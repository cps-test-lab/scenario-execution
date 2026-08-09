# scenario_execution_websocket

Scenario Execution library that talks to a robot over the **rosbridge**
websocket protocol (rosbridge v2), using
[roslibpy](https://github.com/RobotWebTools/roslibpy). It requires **no ROS2 /
rclpy** installation — only a reachable
[`rosbridge_server`](https://github.com/RobotWebTools/rosbridge_suite) on the
robot side.

This makes it possible to drive/observe a ROS system from a laptop, CI, or a
mission-control host that has no ROS installed.

## Installation

```bash
pip install roslibpy   # runtime dependency
# then build/install this package like any other scenario_execution lib
```

## Usage

Import the library in your scenario and use the `rosbridge_*` actions. Every
action takes `host` / `port` (defaults `localhost` / `9090`) pointing at the
rosbridge server. Connections are pooled and shared per `(host, port)`.

```
import osc.helpers
import osc.rosbridge

scenario example:
    do serial:
        rosbridge_wait_for_topics(topics: ['/chatter'], host: '127.0.0.1', port: 9090)
        rosbridge_topic_publish(
            topic_name: '/chatter',
            topic_type: 'std_msgs.msg.String',
            value: '{\"data\": \"hello\"}',
            host: '127.0.0.1')
        rosbridge_check_data(
            topic_name: '/chatter',
            topic_type: 'std_msgs.msg.String',
            member_name: 'data',
            expected_value: 'hello',
            eval_expected_value: false,
            host: '127.0.0.1')
```

## Actions

| Action | Purpose |
|---|---|
| `rosbridge_topic_publish` | Publish a message to a topic |
| `rosbridge_topic_monitor` | Subscribe and store the latest message into a variable |
| `rosbridge_wait_for_data` | Wait for any message on a topic |
| `rosbridge_check_data` | Compare received messages against an expected value |
| `rosbridge_service_call` | Call a service and optionally store the response |
| `rosbridge_action_call` | Send a ROS2 action goal (rosbridge v2 `send_action_goal`) |
| `rosbridge_wait_for_topics` | Wait until topics are advertised (via `/rosapi`) |
| `rosbridge_wait_for_services` | Wait until services are available (via `/rosapi`) |
| `rosbridge_get_parameter` | Read a parameter (via `/rosapi`) into a variable |
| `rosbridge_set_parameter` | Set a parameter (via `/rosapi`) |

Type strings use the same `.`-separated convention as `scenario_execution_ros`
(e.g. `std_msgs.msg.String`, `example_interfaces.action.Fibonacci`); they are
converted internally to the rosbridge `/`-separated form.

## Notes

- Requires `roslibpy >= 2.0` for ROS2 action support (`send_action_goal`).
- rosbridge does not expose the full ROS QoS model; `rosbridge_topic_publish`
  exposes only the transport knobs rosbridge supports (`latch`, `queue_size`).
- ROS2 parameters are node-scoped: pass `name` as `node_name:parameter_name`.
