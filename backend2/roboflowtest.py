from inference import get_model
import supervision as sv
from inference_sdk import InferenceHTTPClient
import interpreter as itp
import os

# Replace with your model's project name and version number
MODEL_ID = "custom-workflow-9"
IMAGE_PATH = "./testImages/"
results = []

from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="yFWsGeKJMvinDuwIkS1B"
)

for f in os.listdir(IMAGE_PATH):
    result = client.run_workflow(
        workspace_name="hackvt25",
        workflow_id= MODEL_ID,
        images={
            "image": IMAGE_PATH + f
        },
        use_cache=True # cache workflow definition for 15 minutes
    )
    print(f"For image path: {IMAGE_PATH + f}")
    print(result[0]['predictions']['predictions'])
    try:
        classID = result[0]['predictions']['predictions'][0]['class'] # grabs just the classification
        print(classID) 
        results.append(classID)
        print(results)
        itp.useClient(str(results))
    except:
        print("No prediction found")
    print()
    