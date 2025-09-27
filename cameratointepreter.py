#!/usr/bin/env python3

"""
camera_app.py - Simple webcam "camera app" using OpenCV.

Controls:
  ESC    : quit
"""

import cv2
from inference import get_model
import supervision as sv
from inference_sdk import InferenceHTTPClient
import interpreter as itp
import os
import threading

# Replace with your model's project name and version number
MODEL_ID = "custom-workflow-9"
IMAGE_PATH = "./testImages/"
FRAME_SKIP = 15 #After FRAME_SKIP amount of frames, use one frame to input into the CV model
results = []

from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="yFWsGeKJMvinDuwIkS1B"
)

def main():

    # Open default camera (index 0)
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    window_name = "Webcam"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    # cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN) # Set to full screen

    print("Press ESC to quit.")

    counter = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break

        # Show frame
        cv2.imshow(window_name, frame)

        # # Pre process the frame using opencv's dnn preprocessing
        # blob = cv2.dnn.blobFromImage(
        # frame,
        # 1/255.0,
        # (416, 416), # Use your model's required size
        # swapRB=True,
        # crop=False
        # )

        counter += 1

        if counter % FRAME_SKIP == 0:
            t1 = threading.Thread(target=predict, args=(frame,))
            t1.daemon = True
            t1.start()
        # ESC to quit
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

def predict(frame):
    global results 

    # print("Called!")
    result = client.run_workflow(
        workspace_name="hackvt25",
        workflow_id= MODEL_ID,
        images={
            "image": frame
        },
        use_cache=True # cache workflow definition for 15 minutes
    )
    # print(f"For image path: {IMAGE_PATH + f}")
    # print(result[0]['predictions']['predictions'])
    try:
        classID = result[0]['predictions']['predictions'][0]['class'] # grabs just the classification
        print(classID) 
        results.append(classID)
        # itp.useClient(str(results))
    except:
        pass
        # print("No prediction found")
    
    # print(results)

    if len(results) >= 5:
        itp.useClient(str(results))
        results = results[2:]

    # print()


if __name__ == "__main__":
    main()