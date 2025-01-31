import time
import argparse
import subprocess
import os
from os.path import join

import numpy as np
import rospy
import rospkg

from geometry_msgs.msg import Twist, PointStamped
from gazebo_simulation import GazeboSimulation

INIT_POSITION = [-2, 3, 1.57]  # in world frame
GOAL_POSITION = [0, 10]  # relative to the initial position

def compute_distance(p1, p2):
    # 返回欧氏距离
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

def path_coord_to_gazebo_coord(x, y):
    RADIUS = 0.075
    r_shift = -RADIUS - (30 * RADIUS * 2)
    c_shift = RADIUS + 5

    gazebo_x = x * (RADIUS * 2) + r_shift
    gazebo_y = y * (RADIUS * 2) + c_shift

    return (gazebo_x, gazebo_y)

def pub_goal_point(goal_point):
    _pub_goal_point = rospy.Publisher('/goal_point', PointStamped, queue_size=1)
    _pub_goal_point.publish(goal_point)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = 'test BARN navigation challenge')
    # 不同世界对应的系数
    parser.add_argument('--world_idx', type=int, default=0)
    
    # TODO: TEST MAP 50, 150, 200
    # 是否打开gazebo的gui界面
    parser.add_argument('--gui', action="store_true")
    # 将结果写入txt文本
    parser.add_argument('--out', type=str, default="out.txt")
    args = parser.parse_args()
    
    ##########################################################################################
    ## 0. Launch Gazebo Simulation
    ##########################################################################################
    
    # 设置系统变量
    os.environ["JACKAL_LASER"] = "1"
    os.environ["JACKAL_LASER_MODEL"] = "ust10"
    os.environ["JACKAL_LASER_OFFSET"] = "-0.065 0 0.01"
    
    world_name = "BARN/world_%d.world" %(args.world_idx)
    print(">>>>>>>>>>>>>>>>>> Loading Gazebo Simulation with %s <<<<<<<<<<<<<<<<<<" %(world_name))   
    # 返回jackal_helper的路径
    rospack = rospkg.RosPack()
    base_path = rospack.get_path('jackal_helper')
    
    launch_file = join(base_path, 'launch', 'gazebo_launch.launch')
    world_name = join(base_path, "worlds", world_name)
    
    # 子进程用于打开gazebo模型，包括世界和机器人
    gazebo_process = subprocess.Popen([
        'roslaunch',
        launch_file,
        'world_name:=' + world_name,
        'world_index:=' + str(args.world_idx),
        'dx:=' + str(INIT_POSITION[0]),
        'dy:=' + str(INIT_POSITION[1]),
        'dtheta:=' + str(INIT_POSITION[2]),
        'gui:=' + ("true" if args.gui else "false")
    ])

    # rviz_tool_path = rospack.get_path('rviz_tool')
    # rviz_launch_file = join(rviz_tool_path, 'launch', 'visualize.launch')
    # # 打开rviz可视化
    # rviz_process = subprocess.Popen([
    #     'roslaunch',
    #     rviz_launch_file,
    # ])

    time.sleep(7)  # sleep to wait until the gazebo being created
    # 初始化节点
    rospy.init_node('gym', anonymous=True) #, log_level=rospy.FATAL)
    rospy.set_param('/use_sim_time', True)
    
    # GazeboSimulation provides useful interface to communicate with gazebo  
    gazebo_sim = GazeboSimulation(init_position=INIT_POSITION)
    
    init_coor = (INIT_POSITION[0], INIT_POSITION[1])
    goal_coor = (INIT_POSITION[0] + GOAL_POSITION[0], INIT_POSITION[1] + GOAL_POSITION[1])

    # 发送目标位置
    goal_point = PointStamped()
    goal_point.header.frame_id = 'odom'
    goal_point.point.x = GOAL_POSITION[0]
    goal_point.point.y = GOAL_POSITION[1]

    # 获取当前机器人的位置信息
    pos = gazebo_sim.get_model_state().pose.position
    curr_coor = (pos.x, pos.y)
    collided = True
    
    # 如果当前位置离机器人位置大于0.1或collided，reset机器人至初始位置
    while compute_distance(init_coor, curr_coor) > 0.1 or collided:
        gazebo_sim.reset() # Reset to the initial position
        pos = gazebo_sim.get_model_state().pose.position
        curr_coor = (pos.x, pos.y)
        collided = gazebo_sim.get_hard_collision()
        time.sleep(1)




    ##########################################################################################
    ## 1. Launch your navigation stack
    ## (Customize this block to add your own navigation stack)
    ##########################################################################################
    
    
    # TODO: WRITE YOUR OWN NAVIGATION ALGORITHMS HERE
    # get laser data : data = gazebo_sim.get_laser_scan()
    # publish your final control through the topic /cmd_vel using : gazebo_sim.pub_cmd_vel([v, w])
    # if the global map is needed, read the map files, e.g. /jackal_helper/worlds/BARN/map_files/map_pgm_xxx.pgm
    
    # DWA example
    launch_file = join(base_path, '..', 'jackal_helper/launch/move_base_teb.launch')
    # launch_file = join(base_path, '..', 'jackal_helper/launch/move_base_DWA.launch')
    nav_stack_process = subprocess.Popen([
        'roslaunch',
        launch_file,
    ])
    
    # Make sure your navigation stack recives a goal of (0, 10, 0), which is 10 meters away
    # along postive y-axis.
    import actionlib
    from geometry_msgs.msg import Quaternion
    from move_base_msgs.msg import MoveBaseGoal, MoveBaseAction
    nav_as = actionlib.SimpleActionClient('/move_base', MoveBaseAction)
    mb_goal = MoveBaseGoal()
    mb_goal.target_pose.header.frame_id = 'odom'
    mb_goal.target_pose.pose.position.x = GOAL_POSITION[0]
    mb_goal.target_pose.pose.position.y = GOAL_POSITION[1]
    mb_goal.target_pose.pose.position.z = 0
    mb_goal.target_pose.pose.orientation = Quaternion(0, 0, 0, 1)
    # 采用action通信发送目标位置
    nav_as.wait_for_server()
    nav_as.send_goal(mb_goal)

    ##########################################################################################
    ## 2. Start navigation
    ##########################################################################################
    
    # 当前时间和当前坐标
    curr_time = rospy.get_time()
    pos = gazebo_sim.get_model_state().pose.position
    curr_coor = (pos.x, pos.y)

    
    # check whether the robot started to move，距离大于0.1才能跳出循环
    while compute_distance(init_coor, curr_coor) < 0.1:
        curr_time = rospy.get_time()
        pos = gazebo_sim.get_model_state().pose.position
        curr_coor = (pos.x, pos.y)
        time.sleep(0.01)
    
    # start navigation, check position, time and collision
    start_time = curr_time
    start_time_cpu = time.time()
    collided = False
    
    # 结束循环条件：与目标距离小于1 && 发生碰撞 && 总时长大于100
    while compute_distance(goal_coor, curr_coor) > 1 and not collided and curr_time - start_time < 100:
        curr_time = rospy.get_time()
        pos = gazebo_sim.get_model_state().pose.position
        curr_coor = (pos.x, pos.y)
        # 打印当前的位置信息  \r:返回当前行的最开始位置
        print("Time: %.2f (s), x: %.2f (m), y: %.2f (m), Distance to goal: %.2f" %(curr_time - start_time, *curr_coor, compute_distance(goal_coor, curr_coor)), end="\r")
        pub_goal_point(goal_point)
        collided = gazebo_sim.get_hard_collision()
        # 每0.1秒循环一次，否则sleep
        while rospy.get_time() - curr_time < 0.1:
            time.sleep(0.01)


    
    
    ##########################################################################################
    ## 3. Report metrics and generate log
    ##########################################################################################
    
    print(">>>>>>>>>>>>>>>>>> Test finished! <<<<<<<<<<<<<<<<<<")
    success = False
    if collided:
        status = "collided"
    elif curr_time - start_time >= 100:
        status = "timeout"
    else:
        status = "succeeded"
        success = True
    print("Navigation %s with time %.4f (s)" %(status, curr_time - start_time))
    
    # 从npy文件中读取np数组，np数组为x y坐标集合
    path_file_name = join(base_path, "worlds/BARN/path_files", "path_%d.npy" %args.world_idx)
    path_array = np.load(path_file_name)
    # 转换为gazebo坐标系下的坐标
    path_array = [path_coord_to_gazebo_coord(*p) for p in path_array]
    # 插入起始坐标和终止坐标
    path_array = np.insert(path_array, 0, (INIT_POSITION[0], INIT_POSITION[1]), axis=0)
    path_array = np.insert(path_array, len(path_array), (INIT_POSITION[0] + GOAL_POSITION[0], INIT_POSITION[1] + GOAL_POSITION[1]), axis=0)
    # 计算路径长度，分别是前一个点对应后一个点之间的距离
    path_length = 0
    for p1, p2 in zip(path_array[:-1], path_array[1:]):
        path_length += compute_distance(p1, p2)
    
    # Navigation metric: 1_success *  optimal_time / clip(actual_time, 4 * optimal_time, 8 * optimal_time)
    optimal_time = path_length / 2
    actual_time = curr_time - start_time
    # 评价指标
    nav_metric = int(success) * optimal_time / np.clip(actual_time, 4 * optimal_time, 8 * optimal_time)
    print("Navigation metric: %.4f" %(nav_metric))
    
    with open(args.out, "a") as f:
        # 结果输出，世界系数、是否成功、是否碰撞、时间是否大于100s、总时间、导航指标
        f.write("%d %d %d %d %.4f %.4f\n" %(args.world_idx, success, collided, (curr_time - start_time)>=100, curr_time - start_time, nav_metric))
    
    # 终止gui程序
    gazebo_process.terminate()
    nav_stack_process.terminate()
