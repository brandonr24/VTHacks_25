#!/usr/bin/env python3

"""
camera_app.py - Simple webcam "camera app" using OpenCV.

Controls:
  SPACE  : take a photo (saved into photos/)
  r      : start/stop video recording (saved into videos/)
  c      : switch to next camera index
  f      : toggle fullscreen
  ESC    : quit
"""

import cv2

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

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break

        # Show frame
        cv2.imshow(window_name, frame)

        # Pre process the frame using opencv's dnn preprocessing
        blob = cv2.dnn.blobFromImage(
        frame,
        1/255.0,
        (416, 416), # Use your model's required size
        swapRB=True,
        crop=False
        )

        

        # ESC to quit
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()