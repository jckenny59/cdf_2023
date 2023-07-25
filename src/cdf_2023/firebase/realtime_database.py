from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import json
import pyrebase
import os


config = {
    "apiKey": "AIzaSyAO_YVROUIc866BqgWgcBpPxUe6SVG5O9g",
    "authDomain": "cdf-project-f570f.firebaseapp.com",
    "databaseURL": "https://cdf-project-f570f-default-rtdb.europe-west1.firebasedatabase.app",
    "projectId": "cdf-project-f570f",
    "storageBucket": "cdf-project-f570f.appspot.com",
    "messagingSenderId": "641027065982",
    "appId": "1:641027065982:web:20ca92f0a2326bc3dab02f",
    "measurementId": "G-RZ5BVHNGK8"
}

# initialize the connection to firebase
firebase = pyrebase.initialize_app(config)

# reference to firebase database
db = firebase.database()


def stream_handler(message):
    print(message["event"])
    print(message["path"])
    print(message["data"])


def set_json_data(json_f, parentname, keys):
    with open(json_f) as json_file:
        json_data = json.load(json_file)
        children = []
        for key in keys:
            values = json_data[key]
            children.append(values)

    for child, key in zip(children, keys):
        db.child(parentname).child(key).set(child)


def set_json_data_joints(json_f):
    with open(json_f) as json_file:
        json_data = json.load(json_file)

    db.child("Joints").set(json_data)


def set_qr_frames(json_fr):
    with open(json_fr) as json_file:
        json_data = json.load(json_file)

    db.child("QRFrames").set(json_data)


# get keys_built
def get_keys_built():
    keys_built = []
    keys = db.child("Built Keys").get()
    if keys.each():
        for key in keys.each():
            # print("key to built key ", key.key())
            keys_built.append(key.val())
    return keys_built


def set_keys_built(keys):
    data = {}
    for key in keys:
        data[str(key)] = str(key)
    db.child("Built Keys").set(data)


def remove_key_built(key):
    db.child("Built Keys").child(str(key)).remove()


def update_robot_frame(index, robot_frame, frame):
    db.child("Design").child("node").child(str(index)).child(robot_frame).set(frame)


def add_key_built(new_key_built):
    db.child("Built Keys").update({str(new_key_built): str(new_key_built)})


# get users' ids
def get_users():
    users_ids = []
    users = db.child("Users").get()
    for user in users.each():
        print(user.key())
        users_ids.append(user.key())
        # print("Selected Key is ", user.val()["selectedKey"])
        # print("Selected by user Nr.", user.val()["userID"])
    return users_ids


def get_users_attribute(attribute):
    users_attributes = []
    users = db.child("user").get()
    for user in users.each():
        users_attributes.append(user.val()[attribute])
    return users_attributes


def get_json_data(name, childname):
    json_data = {}
    data = db.child(name).child(childname).get()
    if data.each():
        for d in data.each():
            json_data[d.key()] = d.val()
        return json_data
    else:
        dt = db.child(name).child(childname).get().val()
        return dt


def listen():
    pass
    # my_stream = db.child("Built Keys").stream(stream_handler)

# add a stream_id for multiple streams
# my_stream = db.child("posts").stream(stream_handler, stream_id="new_post")


def close_stream(my_stream):
    my_stream.close()


if __name__ == "__main__":

    # add_key_built(4)
    # remove_key_built(10)
    print(get_keys_built())
    # my_stream = db.child("Built Keys").stream(stream_handler)
    # my_stream = db.child("Users").stream(stream_handler)
    # close_stream(my_stream)
    # remove_key_built(17)
