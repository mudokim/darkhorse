import math
import json
import random
import time
import rclpy
from rclpy.node import Node
from modules.base_bt_nodes import (
    BTNodeList, Status, SyncAction, Node,
    Sequence, Fallback, ReactiveSequence, ReactiveFallback, Parallel,
)
from modules.base_bt_nodes_ros import ActionWithROSAction, ConditionWithROSTopics

# ROS 2 Messages
from limo_interfaces.action import Speak as speakActionMsg
from std_msgs.msg import String, Bool
from nav2_msgs.action import NavigateToPose
from action_msgs.msg import GoalStatus
from nav_msgs.msg import Odometry

# ==========================================
# 상수 및 좌표 정의
# ==========================================
INFO_DESK_NAME = "안내데스크"
DEPARTMENT_COORDINATES = {
    "진단검사의학과": {"x": -2.0478696823120117, "y": 1.3148077726364136, "w": 1.0},
    "정형외과":      {"x": 4.325248718261719, "y": -1.067739486694336, "w": 1.0},
    "안내데스크":    {"x": 0.08828259259462357, "y": 0.08828259259462357, "w": 1.0},
}
DEFAULT_DEPARTMENTS = ["진단검사의학과", "정형외과"]


def publish_ui_status(ros_node, text):
    pub = ros_node.create_publisher(String, '/hospital/nav_status', 10)
    msg = String()
    msg.data = text
    pub.publish(msg)

# ==========================================
# Action Nodes
# ==========================================

class GoToInfoDesk(ActionWithROSAction):
    def __init__(self, name, agent):
        super().__init__(name, agent, (NavigateToPose, '/navigate_to_pose'))
        self.timeout_sec = 60.0
        self.start_time = None
        self.nav_goal_sent = False

    def _build_goal(self, agent, bb):
        coords = DEPARTMENT_COORDINATES.get(INFO_DESK_NAME)
        if not coords:
            return None

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.ros.node.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(coords['x'])
        goal.pose.pose.position.y = float(coords['y'])
        goal.pose.pose.orientation.w = float(coords.get('w', 1.0))

        publish_ui_status(self.ros.node, "안내데스크 복귀 중 🏠")
        print("[GoToInfoDesk] 🏠 안내데스크로 복귀 시작")

        self.start_time = self.ros.node.get_clock().now()
        self.nav_goal_sent = True
        return goal

    async def run(self, agent, bb):
        status = await super().run(agent, bb)

        if status == Status.RUNNING and self.nav_goal_sent:
            now = self.ros.node.get_clock().now()
            elapsed_time = (now - self.start_time).nanoseconds / 1e9
            if elapsed_time > self.timeout_sec:
                print("[GoToInfoDesk] ⚠️ Timeout -> force success")
                if self._action_client and self._goal_handle:
                    self._action_client.cancel_goal_async(self._goal_handle)
                self.nav_goal_sent = False
                return Status.SUCCESS

        return status

    def _interpret_result(self, result, agent, bb, status_code=None):
        self.nav_goal_sent = False

        if status_code == GoalStatus.STATUS_SUCCEEDED:
            print("[GoToInfoDesk] ✅ 도착 완료")
            return Status.SUCCESS

        if bb.get('abort', False):
            print("[GoToInfoDesk] ⚠️ abort 상태 -> 성공 처리")
            return Status.SUCCESS

        print(f"[GoToInfoDesk] ❌ 이동 실패 (code={status_code})")
        return Status.FAILURE


class WaitForQR(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)
        self.received_msg = None
        self.done = False
        self.first_run = True
        agent.ros_bridge.node.create_subscription(
            String, "/hospital/qr_login", self._callback, 10
        )

    def _callback(self, msg):
        self.received_msg = msg

    def _tick(self, agent, bb):
        if self.first_run:
            publish_ui_status(agent.ros_bridge.node, "환자 접수 대기 중... 📋")
            bb['abort'] = False
            self.first_run = False

        if self.done:
            return Status.SUCCESS

        if self.received_msg is None:
            return Status.RUNNING

        try:
            data = json.loads(self.received_msg.data)
            bb['patient_id'] = data.get("patient_id", "Unknown")

            raw = data.get("departments", DEFAULT_DEPARTMENTS)
            depts = [d for d in raw if d in DEPARTMENT_COORDINATES and d != INFO_DESK_NAME]

            bb['remaining_depts'] = list(depts)
            bb['visited_depts'] = set()
            bb['speak_text'] = "접수가 완료되었습니다."

            publish_ui_status(agent.ros_bridge.node, "접수 완료 ✅")
            self.done = True
            self.received_msg = None
            return Status.SUCCESS

        except Exception:
            self.received_msg = None
            return Status.RUNNING


class Think(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)

    def _tick(self, agent, bb):
        remaining = bb.get('remaining_depts', [])
        visited = bb.get('visited_depts', set())

        remaining = [d for d in remaining if d not in visited]

        if not remaining:
            return Status.FAILURE

        next_dept = random.choice(remaining)
        coords = DEPARTMENT_COORDINATES.get(next_dept)
        if not coords:
            return Status.RUNNING

        visited.add(next_dept)
        bb['visited_depts'] = visited
        bb['current_target_name'] = next_dept
        bb['current_target_coords'] = coords
        bb['speak_text'] = f"{next_dept}로 이동하겠습니다."

        return Status.SUCCESS


class Move(ActionWithROSAction):
    def __init__(self, name, agent):
        super().__init__(name, agent, (NavigateToPose, '/navigate_to_pose'))

    def _build_goal(self, agent, bb):
        coords = bb.get('current_target_coords')
        if not coords:
            return None

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.ros.node.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(coords['x'])
        goal.pose.pose.position.y = float(coords['y'])
        goal.pose.pose.orientation.w = float(coords.get('w', 1.0))

        publish_ui_status(self.ros.node, f"{bb.get('current_target_name')} 이동 중 🚑")
        return goal

    def _interpret_result(self, result, agent, bb, status_code=None):
        if status_code == GoalStatus.STATUS_SUCCEEDED:
            bb['speak_text'] = f"{bb.get('current_target_name')}에 도착했습니다."
            return Status.SUCCESS

        bb['speak_text'] = "이동에 실패했습니다."
        return Status.FAILURE


class WaitDoctorDone(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)
        self.done = False
        agent.ros_bridge.node.create_subscription(
            Bool, "/hospital/doctor_input", self._cb, 10
        )

    def _cb(self, msg):
        if msg.data:
            self.done = True

    def _tick(self, agent, bb):
        if not self.done:
            publish_ui_status(agent.ros_bridge.node, "진료 중... 👨‍⚕️")
            return Status.RUNNING

        self.done = False
        bb['speak_text'] = "진료가 끝났습니다."
        return Status.SUCCESS


class SpeakAction(ActionWithROSAction):
    def __init__(self, name, agent):
        super().__init__(name, agent, (speakActionMsg, 'speak_text'))

    def _build_goal(self, agent, bb):
        text = bb.pop('speak_text', None)
        if not text:
            return None
        goal = speakActionMsg.Goal()
        goal.text = text
        return goal


class WaitSpeedOK(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)
        self.limit = 0.8
        self._odom = None
        agent.ros_bridge.node.create_subscription(
            Odometry, "/odom", self._cb, 10
        )

    def _cb(self, msg):
        self._odom = msg

    def _tick(self, agent, bb):
        if self._odom is None:
            return Status.SUCCESS
        return Status.SUCCESS


# ==========================================
# 🔥 핵심 수정 포인트
# ==========================================

class IsEmergencyPressed(ConditionWithROSTopics):
    """
    ✅ abort 플래그 제거
    → 오직 emergency_trigger 토픽만 본다
    """
    def __init__(self, name, agent):
        super().__init__(name, agent, [(Bool, "/emergency_trigger", "emergency_flag")])

    async def run(self, agent, bb):
        if "emergency_flag" not in self._cache:
            return Status.FAILURE
        return Status.SUCCESS if self._cache["emergency_flag"].data else Status.FAILURE


class SetAbort(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)

    def _tick(self, agent, bb):
        bb['abort'] = True
        bb['speak_text'] = "비상 상황 발생! 복귀합니다."
        return Status.SUCCESS


class NotAbort(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)

    def _tick(self, agent, bb):
        return Status.FAILURE if bb.get('abort', False) else Status.SUCCESS


class ControlSiren(SyncAction):
    """
    ✅ 엣지 트리거 방식
    → 같은 True/False는 재전송 안 함
    """
    def __init__(self, name, agent, enable=True, **kwargs):
        super().__init__(name, self._tick)
        self.pub = agent.ros_bridge.node.create_publisher(Bool, "/cmd_siren", 10)
        self.enable = bool(enable)
        self.last_sent = None

    def _tick(self, agent, bb):
        if self.last_sent == self.enable:
            return Status.SUCCESS

        msg = Bool()
        msg.data = self.enable
        self.pub.publish(msg)
        self.last_sent = self.enable

        state = "ON" if self.enable else "OFF"
        print(f"[ControlSiren] {state}")
        return Status.SUCCESS


class SendDiagnosisEmail(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._tick)
        self.pub = agent.ros_bridge.node.create_publisher(
            String, "/hospital/send_diagnosis_email", 10
        )

    def _tick(self, agent, bb):
        payload = {
            "patient_id": bb.get("patient_id"),
            "request": "send_diagnosis_email"
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.pub.publish(msg)
        return Status.SUCCESS


class KeepRunningUntilFailure(Node):
    def __init__(self, name, children=None):
        super().__init__(name)
        self.children = children or []

    async def run(self, agent, bb):
        status = await self.children[0].run(agent, bb)
        return Status.SUCCESS if status == Status.FAILURE else Status.RUNNING


# ==========================================
# 노드 등록
# ==========================================

BTNodeList.ACTION_NODES.extend([
    'WaitForQR', 'SpeakAction', 'Think', 'WaitSpeedOK', 'Move',
    'WaitDoctorDone', 'GoToInfoDesk', 'SendDiagnosisEmail',
    'SetAbort', 'NotAbort', 'ControlSiren'
])

BTNodeList.CONDITION_NODES.extend([
    'IsEmergencyPressed'
])

BTNodeList.CONTROL_NODES.append('KeepRunningUntilFailure')

print("✅ bt_nodes.py (siren 안정화 버전) 로드 완료")
