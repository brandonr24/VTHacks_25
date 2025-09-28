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
MODEL_ID = "custom-workflow-10"
IMAGE_PATH = "./testImages/"
FRAME_SKIP = 15 #After FRAME_SKIP amount of frames, use one frame to input into the CV model
FRAME_SKIP_RATIO = 4 
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

        # # Pre process the frame using opencv's dnn preprocessing
        # blob = cv2.dnn.blobFromImage(
        # frame,
        # 1/255.0,
        # (416, 416), # Use your model's required size
        # swapRB=True,
        # crop=False
        # )
        # print(counter) 

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

    # print("Called!")
    result = client.run_workflow(
        workspace_name="hackvt25",
        workflow_id= MODEL_ID,
        images={
            "image": frame
        },
        use_cache=True # cache workflow definition for 15 minutes
    )
    # print(result)
    # print(f"For image path: {IMAGE_PATH + f}")
    # print(result[0]['predictions']['predictions'])
    try:
        # classID = result[0]['predictions']['predictions'][0]['class'] # grabs just the classification
        # confidence = result[0]['predictions']['predictions'][0]['confidence'] # grabs just the confidence
        # Take the classification with the highest confidence
        for pred in result[0]:
            # print(result[0][pred])
            try:
                classID = result[0][pred]['predictions'][0]['class']
                results.append(classID)
                print(classID, result[0][pred]['predictions'][0]['confidence'], len(results)) 
                # print(pred['predictions'][0]['class'])
                # if confidence < pred['predictions'][0]['confidence']:
                #     confidence = pred['predictions'][0]['confidence']
                #     classID = pred['predictions'][0]['class']
            except:
                # print("Exception occured")
                # print(pred)
                pass
                

        # results.append(classID)

        # try:
        #     secondBestID = result[0]['predictions']['predictions'][1]['class'] # grabs just the classification
        #     results.append(secondBestID)
        # except:
        #     pass

        # print()
        # print(results)
        # itp.useClient(str(results))
    except:
        pass
        # print("No prediction found")
    
    # print(results)

    # if len(results) >= 5:
    #     itp.useClient(str(results))
        # results = results[2:]

    # print()


if __name__ == "__main__":
    main()