# Darkhorse — LIMO Hospital Guide Robot

ROS2 Nav2와 Behavior Tree를 이용해 **병원 건강검진 환경에서 환자를 목적지까지 안내하고, 검진 후 복귀하며, 비상 상황에도 정해진 절차로 대응하는 LIMO 기반 안내 로봇 시스템**을 구현한 프로젝트입니다.

단순히 Nav2 goal을 보내는 기능에 그치지 않고, 병원 서비스 시나리오에 맞게 **목적지 선택 → 자율주행 → 검진 대기 → 복귀 → 비상 대응** 흐름을 하나의 시스템으로 연결했습니다.

## Project Overview

| Item | Description |
| --- | --- |
| Platform | AgileX LIMO |
| Middleware | ROS2 |
| Navigation | Nav2 / `nav2_simple_commander` |
| Behavior | Behavior Tree |
| Language | Python / C++ |
| Main Topics | destination dispatch, speed control, emergency stop/resume |

## Key Features

- 병원에서 사용할 진료과를 선택하는 초기 설정 기능
- 진료과 이름을 Nav2 goal pose로 변환해 목적지까지 안내
- 안내 완료 후 원점 복귀 시나리오
- Nav2 주행 속도 동적 조절
- 비상 버튼 입력 시 즉시 navigation task 취소
- 비상 상황 종료 후 이전 목적지 또는 복귀 흐름 재개
- Behavior Tree 기반 정상 안내 / 비상 대응 흐름 분리
- 병원 환경을 고려한 보수적인 속도·장애물 회피·정지 거리 튜닝

## System Flow

```text
병원 진료과 설정
        ↓
사용자 목적지 선택
        ↓
/dispatch_target
        ↓
Smart Dispatcher
        ↓
Destination → PoseStamped
        ↓
Nav2 BasicNavigator
        ↓
LIMO 자율주행
        ↓
검진 / 대기
        ↓
복귀 또는 다음 행동
```

비상 상황에서는 정상 navigation 흐름보다 emergency branch가 우선하도록 구성했습니다.

```text
Emergency Input
      ↓
현재 Nav2 task 취소
      ↓
STOPPED (EMERGENCY)
      ↓
안내 / 사이렌
      ↓
비상 해제
      ↓
기존 목적지 또는 복귀 흐름 재개
```

## What I Implemented

### 1. Behavior Tree 기반 행동 로직

병원 안내 서비스를 하나의 긴 코드로 작성하지 않고, 다음 행동을 독립된 단계로 나누어 연결했습니다.

- 안내 시작
- 목적지 이동
- 검진 대기
- 원점 복귀
- 비상 상황 감지
- 비상 대응 및 복귀

각 단계의 성공/실패 조건에 따라 다음 행동으로 전환하도록 구성해, 새로운 목적지나 서비스가 추가되어도 기존 전체 흐름을 크게 수정하지 않고 확장할 수 있도록 했습니다.

### 2. Emergency Scenario

비상 버튼 입력을 별도 조건으로 감지하고 정상 navigation보다 높은 우선순위로 처리했습니다.

비상 상황 발생 시 현재 Nav2 task를 취소하고 상태를 `STOPPED (EMERGENCY)`로 변경한 뒤, 상황 종료 시 기존 흐름을 다시 이어갈 수 있도록 구성했습니다.

### 3. Nav2 Parameter Tuning

기본 Nav2 설정에서는 병원처럼 좁은 환경에서 속도가 지나치게 느리거나, 갑작스러운 장애물 앞에서 정지/회피가 불안정한 문제가 있었습니다.

다음 항목을 반복적으로 조정했습니다.

- controller speed limit
- velocity smoother
- obstacle inflation / safety distance
- stopping distance
- planner / controller behavior

최고 속도보다 **사람과 장애물이 많은 병원 환경에서 안정적으로 멈추고 회피하는 주행**을 우선했습니다.

---

## Hospital Setup

`hospital_setup` 패키지는 병원에서 운영할 진료과를 선택하는 초기 설정 기능을 담당합니다.

지원 진료과:

- 진단검사의학과
- 영상의학과
- 내과
- 정형외과
- 신경과

사용자가 각 진료과의 사용 여부를 `y/n`으로 입력하면 선택 결과를 `~/hospital_config.json`에 저장합니다.

```bash
ros2 run hospital_setup configure
```

## Smart Dispatcher

`smart_dispatcher`는 목적지 이름을 실제 navigation goal로 변환하고 Nav2에 전달합니다.

UI 또는 다른 ROS2 node가 `/dispatch_target`으로 목적지 이름을 전달하면, dispatcher가 해당 목적지의 좌표를 찾아 `PoseStamped`로 변환하고 `BasicNavigator.goToPose()`를 호출합니다.

현재 등록된 목적지 좌표:

| 목적지 | x | y |
| --- | ---: | ---: |
| 진단검사의학과 | 0.4807 | 0.2763 |
| 영상의학과 | 6.5785 | 2.6214 |
| 내과 | 7.4453 | 0.5102 |
| 정형외과 | 0.7539 | -2.6409 |
| 신경과 | 2.8364 | 1.1752 |

## Speed Control

주행 중 `/nav_speed_delta`로 속도 증감 값을 전달하면 현재 속도를 변경합니다.

속도는 **0.10 m/s ~ 0.40 m/s** 범위로 제한하고, 변경된 값은 Nav2 `controller_server`와 `velocity_smoother`에 반영합니다.

주요 적용 파라미터:

```text
/controller_server
└── FollowPath.max_vel_x

/velocity_smoother
└── max_velocity
```

## Emergency Stop / Resume

`/nav_emergency` 토픽으로 긴급 정지와 재개를 제어합니다.

### Emergency ON

```text
/nav_emergency = True
→ 현재 Nav2 task cancel
→ STOPPED (EMERGENCY)
```

### Emergency OFF

```text
/nav_emergency = False
→ 저장된 목적지 확인
→ navigation 재개
→ MOVING
```

## ROS2 Topics

### Subscribe

| Topic | Type | Description |
| --- | --- | --- |
| `/dispatch_target` | `std_msgs/String` | 이동할 진료과 이름 |
| `/nav_speed_delta` | `std_msgs/Float32` | 현재 속도 변화량 |
| `/nav_emergency` | `std_msgs/Bool` | 긴급 정지 / 재개 |

### Publish

| Topic | Type | Description |
| --- | --- | --- |
| `/nav_status` | `std_msgs/String` | 현재 로봇 상태 |
| `/nav_current_speed` | `std_msgs/Float32` | 현재 주행 속도 |
| `/nav_current_target` | `std_msgs/String` | 현재 이동 목적지 |

## Package Structure

```text
darkhorse/
├── src/
│   ├── hospital_setup/
│   │   ├── hospital_setup/
│   │   │   └── setup_node.py
│   │   ├── package.xml
│   │   └── setup.py
│   │
│   └── smart_dispatcher/
│       ├── smart_dispatcher/
│       │   ├── dispatcher_node.py
│       │   └── smart_dispatcher_node.py
│       ├── package.xml
│       └── setup.py
│
└── README.md
```

## Run

### 1. Build

```bash
cd ~/darkhorse
colcon build
source install/setup.bash
```

### 2. Configure Departments

```bash
ros2 run hospital_setup configure
```

### 3. Start Nav2

LIMO의 SLAM 또는 localization과 Nav2 bringup을 먼저 실행합니다.

### 4. Start Dispatcher

```bash
ros2 run smart_dispatcher dispatcher
```

### 5. Send Destination

```bash
ros2 topic pub /dispatch_target std_msgs/msg/String "{data: '내과'}"
```

### 6. Change Speed

```bash
ros2 topic pub /nav_speed_delta std_msgs/msg/Float32 "{data: 0.05}"
```

### 7. Emergency Stop

```bash
ros2 topic pub /nav_emergency std_msgs/msg/Bool "{data: true}"
```

### 8. Resume

```bash
ros2 topic pub /nav_emergency std_msgs/msg/Bool "{data: false}"
```

## What I Learned

이 프로젝트를 통해 Nav2에서 단순히 goal을 보내는 것보다 **서비스 전체 행동 흐름을 어떻게 설계하는지**가 중요하다는 것을 경험했습니다.

또한 실제 LIMO를 주행시키면서 simulation과 달리 localization, 장애물 센서, 속도, 정지 거리 등 여러 요소가 동시에 navigation 품질에 영향을 준다는 점을 확인했습니다.

Behavior Tree를 적용하면서 정상 안내 흐름과 비상 행동을 분리하고, 각 기능을 독립적인 행동 단위로 구성하는 방법도 경험했습니다.

## Portfolio / Visual Demo

서비스 시나리오, Behavior Tree 구조, 실제 LIMO 주행 사진 및 영상은 아래 포트폴리오 페이지에 정리되어 있습니다.

- [LIMO Hospital Guide Robot · Nav2 + Behavior Tree](https://app.notion.com/p/5a336ae1bc338360863c016e84625bb2)
