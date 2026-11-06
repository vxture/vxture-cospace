"""Small ROS1 byte fixtures; observations and clocks are entirely synthetic."""
import struct
from pathlib import Path

import numpy as np
from rosbags.rosbag1 import Writer
from rosbags.typesys import Stores, get_typestore


def create_bag(path, case='valid', mutate=None):
    store = get_typestore(Stores.ROS1_NOETIC)
    t = store.types
    Time = t['builtin_interfaces/msg/Time']
    Header = t['std_msgs/msg/Header']
    Field = t['sensor_msgs/msg/PointField']
    Vector = t['geometry_msgs/msg/Vector3']
    Quaternion = t['geometry_msgs/msg/Quaternion']
    def header(i,frame):
        return Header(i,Time(100,i*10000000),frame)
    with Writer(Path(path)) as writer:
        lidar = writer.add_connection('/points_raw','sensor_msgs/msg/PointCloud2',typestore=store)
        imu = writer.add_connection('/imu','sensor_msgs/msg/Imu',typestore=store)
        for i in range(21):
            message = t['sensor_msgs/msg/Imu'](header(i,'imu'),Quaternion(0.,0.,0.,1.),np.zeros(9),
                         Vector(0.,0.,0.),np.zeros(9),Vector(0.,0.,9.81),np.zeros(9))
            if case=='backward_imu' and i==10: message.header.stamp.nanosec=0
            if mutate: mutate('imu',i,message)
            if case!='missing_imu': writer.write(imu,100000000000+i*10000000,store.serialize_ros1(message,message.__msgtype__))
            if i%10==0:
                names = ['x','y','z'] if case=='missing_point_time' else ['x','y','z','time']
                fields = [Field(name,n*4,7,1) for n,name in enumerate(names)]
                payload = b''.join(struct.pack('<'+'f'*len(names),*([1.,2.,.5] + ([j*.001] if len(names)==4 else []))) for j in range(2))
                message = t['sensor_msgs/msg/PointCloud2'](header(i,'lidar'),1,2,fields,False,len(names)*4,
                         len(payload),np.frombuffer(payload,dtype=np.uint8).copy(),True)
                if mutate: mutate('lidar',i,message)
                writer.write(lidar,100000000000+i*10000000,store.serialize_ros1(message,message.__msgtype__))
