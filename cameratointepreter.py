#!/usr/bin/env python3

"""
camera_app.py - Simple webcam "camera app" using OpenCV.

Controls:
  ESC    : quit
"""

import cv2
# from inference import get_model
# import supervision as sv
from inference_sdk import InferenceHTTPClient
import interpreter as itp
import os
import threading
import time

# Replace with your model's project name and version number
MODEL_ID = "custom-workflow-11"
IMAGE_PATH = "./testImages/"
FRAME_SKIP = 15 #After FRAME_SKIP amount of frames, use one frame to input into the CV model
FRAME_SKIP_RATIO = 1 
results = []

from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="yFWsGeKJMvinDuwIkS1B"
)

def main():
    global FRAME_SKIP
    # Open default camera (index 0)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    FRAME_SKIP = fps // FRAME_SKIP_RATIO

    window_name = "Webcam"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    # cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN) # Set to full screen

    print("Press ESC to quit.")

    counter = 0
    times_called = 0
    start_time = time.time()
    print(f"Start time is: {start_time}")
    while True:
        curr_time = time.time()
        # print(f"Time difference: {curr_time-start_time}")
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break

        # Show frame
        cv2.imshow(window_name, frame)

        if (counter == 0):
            times_called = 0
            start_time = time.time()

        if counter % FRAME_SKIP == 0:
            # print(counter)
            t1 = threading.Thread(target=predict, args=(frame,))
            t1.daemon = True
            t1.start()
        
        if ((len(results) > 30 and times_called < 3) or 
            (int((curr_time-start_time) + 0.5) > 10 and times_called < 3)): #30 and counter % (FRAME_SKIP*10) == 0:
            # itp.useClient(str(results))
            start_time = time.time()
            print(results)
            t3 = threading.Thread(target=itp.useClient, args=(str(results),))
            t3.daemon = True
            t3.start()

            # Garbage Clean Up
            t2 = threading.Thread(target=cleanUp)
            t2.daemon = True
            t2.start()

            times_called += 1

        # ESC to quit
        if cv2.waitKey(1) & 0xFF == 27:
            break
        
        counter += 1
        counter = counter % (fps*20) # Limit the size of counter as time passes, resets every 20 seconds

    cap.release()
    cv2.destroyAllWindows()

def cleanUp():
    global results
    results = []

def predict(frame):
    global results 

    p_time_start = time.time()
    # print("Called!")
    result = client.run_workflow(
        workspace_name="hackvt25",
        workflow_id= MODEL_ID,
        images={
            "image": frame
        },
        use_cache=True 
    )

    result += client.run_workflow(
        workspace_name="hackvt25",
        workflow_id= MODEL_ID,
        images={
            "image": cv2.flip(frame, 1)
        },
        use_cache=True 
    )

    try:
        # classID = result[0]['predictions']['predictions'][0]['class'] # grabs just the classification
        # confidence = result[0]['predictions']['predictions'][0]['confidence'] # grabs just the confidence
        classID_max = -1
        confidence_max = -1
        # Take the classification with the highest confidence
        for pred in result[0]:
            try:
                if pred != 'output': #'output' gives a bunch of garbage
                    confidence = result[0][pred][0]['predictions'][0]['confidence']
                    if confidence > confidence_max: 
                        classID = result[0][pred][0]['predictions'][0]['class']
                        # print("1", classID, result[0][pred][0]['predictions'][0]['confidence'])#, len(results)) 
                        # print(classID == 1, classID)
                        if classID != "1" and classID != "1 0 0 1 0 1 1 0 1" and classID != "your" and confidence >= 0.4: 
                            confidence_max = confidence
                            classID_max = classID
                            
                            # print("1", classID, confidence, len(results)) 
                if classID_max != -1:
                    results.append(classID_max)
                    print(results, confidence_max)
            except:
                pass
    except:
        pass


if __name__ == "__main__":
    main()