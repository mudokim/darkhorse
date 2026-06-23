# darkhorse
# Darkhorse

LIMO 로봇을 활용한 건강검진 보조 도우미 로봇 프로젝트입니다.
병원 내부에서 환자 또는 방문자가 원하는 진료과로 이동할 수 있도록 목적지를 선택하고, ROS2 Nav2 기반 자율주행을 통해 해당 위치까지 안내하는 구조로 구현했습니다.

## 프로젝트 개요

이 프로젝트는 건강검진 환경에서 LIMO 로봇이 병원 내 주요 진료과를 안내하는 보조 도우미 역할을 수행하도록 만든 ROS2 기반 시스템입니다.

사용자는 병원에서 운영 중인 진료과를 초기 설정으로 등록할 수 있고, 이후 로봇은 선택된 목적지 좌표로 이동합니다.
주행은 Nav2의 `BasicNavigator`를 사용하여 수행하며, 목적지 이동, 속도 조절, 긴급 정지 및 재개 기능을 포함합니다.

## 주요 기능

### 1. 병원 진료과 초기 설정

`hospital_setup` 패키지는 병원에서 사용할 진료과를 선택하는 초기 설정 기능을 담당합니다.

지원하는 진료과 목록은 다음과 같습니다.

* 진단검사의학과
* 영상의학과
* 내과
* 정형외과
* 신경과

사용자가 각 진료과의 사용 여부를 `y/n`으로 입력하면, 선택된 진료과 목록이 `~/hospital_config.json` 파일에 저장됩니다.
이 설정 파일은 이후 로봇이 어떤 진료과를 대상으로 운영될지 결정하는 기준으로 사용됩니다.

### 2. 목적지 기반 자율주행

`smart_dispatcher` 패키지는 실제 로봇의 목적지 이동을 담당합니다.

UI 또는 외부 노드에서 `/dispatch_target` 토픽으로 목적지 이름을 보내면, dispatcher 노드는 해당 이름에 맞는 좌표를 찾아 Nav2 goal pose로 변환합니다.
이후 `BasicNavigator.goToPose()`를 사용하여 로봇을 해당 위치까지 이동시킵니다.

현재 등록된 목적지 좌표는 다음과 같습니다.

| 목적지     |      x |       y |
| ------- | -----: | ------: |
| 진단검사의학과 | 0.4807 |  0.2763 |
| 영상의학과   | 6.5785 |  2.6214 |
| 내과      | 7.4453 |  0.5102 |
| 정형외과    | 0.7539 | -2.6409 |
| 신경과     | 2.8364 |  1.1752 |

### 3. 속도 조절

로봇 주행 중 `/nav_speed_delta` 토픽으로 속도 증감 값을 전달하면, 현재 속도에 해당 값을 더해 주행 속도를 조절합니다.

속도는 최소 0.10 m/s, 최대 0.40 m/s 범위로 제한됩니다.
변경된 속도는 Nav2의 `controller_server`와 `velocity_smoother` 파라미터에 반영됩니다.

적용되는 주요 파라미터는 다음과 같습니다.

* `/controller_server`

  * `FollowPath.max_vel_x`
* `/velocity_smoother`

  * `max_velocity`

### 4. 긴급 정지 및 재개

`/nav_emergency` 토픽을 통해 긴급 정지 기능을 수행합니다.

* `True` 수신 시

  * 현재 Nav2 task를 취소합니다.
  * 로봇 상태를 `STOPPED (EMERGENCY)`로 변경합니다.

* `False` 수신 시

  * 이전 목적지가 저장되어 있으면 해당 목적지로 다시 주행을 시작합니다.
  * 로봇 상태를 다시 `MOVING`으로 변경합니다.

이를 통해 사용자가 위험 상황에서 로봇을 즉시 정지시키고, 필요할 경우 기존 목적지로 다시 안내를 재개할 수 있습니다.

## ROS2 토픽 구조

### Subscribe Topics

| 토픽명                | 메시지 타입             | 설명               |
| ------------------ | ------------------ | ---------------- |
| `/dispatch_target` | `std_msgs/String`  | 이동할 진료과 이름 입력    |
| `/nav_speed_delta` | `std_msgs/Float32` | 현재 속도에 더할 속도 변화량 |
| `/nav_emergency`   | `std_msgs/Bool`    | 긴급 정지 및 재개 명령    |

### Publish Topics

| 토픽명                   | 메시지 타입             | 설명           |
| --------------------- | ------------------ | ------------ |
| `/nav_status`         | `std_msgs/String`  | 현재 로봇 상태     |
| `/nav_current_speed`  | `std_msgs/Float32` | 현재 설정된 주행 속도 |
| `/nav_current_target` | `std_msgs/String`  | 현재 이동 중인 목적지 |

## 패키지 구조

```bash
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

## 실행 방법

### 1. 워크스페이스 빌드

```bash
cd ~/darkhorse
colcon build
source install/setup.bash
```

### 2. 병원 진료과 초기 설정

```bash
ros2 run hospital_setup configure
```

실행 후 사용할 진료과를 `y/n`으로 선택합니다.
설정이 완료되면 `~/hospital_config.json` 파일이 생성됩니다.

### 3. Nav2 실행

LIMO 로봇의 SLAM 또는 Localization, Nav2 bringup이 먼저 실행되어 있어야 합니다.
`smart_dispatcher`는 Nav2가 active 상태가 될 때까지 대기한 뒤 목적지 명령을 처리합니다.

### 4. Dispatcher 실행

```bash
ros2 run smart_dispatcher dispatcher
```

### 5. 목적지 이동 명령 보내기

예시로 내과로 이동하려면 다음 명령을 실행합니다.

```bash
ros2 topic pub /dispatch_target std_msgs/msg/String "{data: '내과'}"
```

다른 목적지 예시는 다음과 같습니다.

```bash
ros2 topic pub /dispatch_target std_msgs/msg/String "{data: '진단검사의학과'}"
ros2 topic pub /dispatch_target std_msgs/msg/String "{data: '영상의학과'}"
ros2 topic pub /dispatch_target std_msgs/msg/String "{data: '정형외과'}"
ros2 topic pub /dispatch_target std_msgs/msg/String "{data: '신경과'}"
```

### 6. 속도 조절

속도를 0.05 m/s 증가시키는 예시입니다.

```bash
ros2 topic pub /nav_speed_delta std_msgs/msg/Float32 "{data: 0.05}"
```

속도를 0.05 m/s 감소시키는 예시입니다.

```bash
ros2 topic pub /nav_speed_delta std_msgs/msg/Float32 "{data: -0.05}"
```

### 7. 긴급 정지

```bash
ros2 topic pub /nav_emergency std_msgs/msg/Bool "{data: true}"
```

### 8. 주행 재개

```bash
ros2 topic pub /nav_emergency std_msgs/msg/Bool "{data: false}"
```

## 전체 동작 흐름

```text
사용자 목적지 선택
        ↓
/dispatch_target 토픽 발행
        ↓
smart_dispatcher 노드에서 목적지 이름 확인
        ↓
목적지 좌표를 PoseStamped로 변환
        ↓
Nav2 BasicNavigator로 goal 전달
        ↓
LIMO 로봇이 목적지까지 자율주행
        ↓
상태 정보 /nav_status로 publish
```

## 핵심 구현 내용

### hospital_setup

병원에서 운영할 진료과를 선택하고, 선택 결과를 JSON 파일로 저장하는 초기 설정 노드입니다.
로봇을 다른 병원 환경에 적용할 때 필요한 진료과만 선택할 수 있도록 구성했습니다.

### smart_dispatcher

목적지 이름을 좌표로 변환하고 Nav2에 goal을 전달하는 주행 명령 노드입니다.
목적지 이동뿐만 아니라 속도 조절, 긴급 정지, 재개 기능까지 함께 처리합니다.

### dispatcher_node

초기 버전의 dispatcher 노드입니다.
설정 파일에서 활성화된 진료과 목록을 불러오고, 각 진료과의 대기 인원을 랜덤으로 생성하여 대기 인원이 가장 적은 과를 추천 목적지로 선택하는 구조입니다.

## 사용 기술

* ROS2
* Python
* Nav2
* nav2_simple_commander
* LIMO mobile robot
* PoseStamped 기반 goal navigation
* ROS2 topic 기반 UI 연동 구조
* JSON 기반 병원 설정 저장

## 프로젝트 의의

이 프로젝트는 단순한 목적지 이동 로봇이 아니라, 병원 건강검진 환경에서 사용할 수 있는 안내 보조 로봇 구조를 목표로 구현되었습니다.
진료과 설정, 목적지 선택, 자율주행, 속도 조절, 긴급 정지 기능을 하나의 흐름으로 연결하여 실제 서비스 로봇의 기본 동작 구조를 구성했습니다.
