from openai import OpenAI

def useClient(input_message):
    try:
        client = OpenAI(api_key="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")
        # while (True):
            # input_message = input("Enter your input words in brackets: ")
            # if input_message == "stop" or input_message == "STOP":
            #     break
        callLLM(client, input_message)

    except Exception as e:
        # Handle the case where the API key is not found or other initial errors
        print(f"Error initializing OpenAI client: {e}")
        # You might need to set the API key explicitly if not using environment variables:
        # client = OpenAI(api_key="YOUR_SECRET_API_KEY") # NOT RECOMMENDED FOR PRODUCTION

def callLLM(client, input_text):
    # Tell the LLM what to do, subject to change
    messages = [
        #Summary of what the job of the AI is
        {"role": "system", "content": "You are to take in a list of "
        + "words which come from a neural network which analyzes video frames and outputs a "
        + "word based on the American Sign Language in the frame reads. You are to interpret this list and turn it into "
        + "an ordered list containing only the true words and ignoring false words. You differentiate between a true and false word "
        + "based on how many continuous duplicates is fed. For example the list: "
        + "[the, the, the, the, one, the, the, quick, quick, quick, quack, quick, quick] " 
        + "would have the output: [the, quick]. It is likely that the actual input will "
        + "contain far more duplicates and more false words. If there is a relatively long string of non-continuous words, "
        + "it is likely that the neural network is outputting garbage because nothing is being signed. Thus, "
        + "ignore these cases."},
        #Example Input
        {"role": "user", "content": "[hi, hi, hi, hi, hi, hi, hi, bye, bye, hi, hi, hi, hi, no, hi, hi, hi, bye, hi, "
         + "hi, yes, no, no, hi, hi, my, my, my, my, my, my, my, my, your, my, my, my, eye, my, my, name, name, name, "
         + "name, name, hi, name, name, the, name, name, name, is, is, is, is, is, not, is, is, is, is, not, is, is, is, "
         + "is, is, is, is, is, John, John, John, John, John, good, John, John, John, John, John, John, John, John]"},
        #Example Response to input
        {"role": "assistant", "content": "[hi, my, name, is, John]"},
        #Example Input 2
        {"role": "user", "content": "[those, those, those, those, who, those, those, those]"},
        #Example Response to input
        {"role": "assistant", "content": "[those]"},
        {"role": "user", "content": "[the, the, the]"}, # smaller scale examples so the model knows to go off of relative scale
        {"role": "assistant", "content": "[the]"},
        # garbage case
        {"role": "user", "content": "[Ephemeral, Zephyr, Quasar, Labyrinth, Serendipity, Mellifluous, Zenith, Solitude, Capricious, "
        + "Luminescent, Equinox, Susurrus, Ponder, Voracious, Glimmer, Tundra, Helix, Obfuscate, Pristine, Wander]"}, 
        {"role": "assistant", "content": "[]"},
        {"role": "user", "content": "[O, O, O, O, O, O, K, O, O, O, O, O, O, O, K, O, O, O]"}, 
        {"role": "assistant", "content": "[O]"},
        {"role": "user", "content": "[Name, Name, Name, Name, Name, Name, F, F, F, F, F, F, O, O, F, F, O, F]"}, 
        {"role": "assistant", "content": "[Name, F]"},
    ]

    try:
        response = client.chat.completions.create(
        model="gpt-4o-mini", # model subject to change
        messages=messages+[{"role": "user", "content": input_text}] 
        )

        # 4. Extract the response text
        # The actual response content is within the 'choices' list
        if response.choices:
            assistant_response = response.choices[0].message.content
            print("Assistant's Response:")
            print(assistant_response)
        else:
            print("No response choices received.")
    
    except Exception as e:
        print(f"An error occurred during the API call: {e}")
"""
if __name__ == "__main__":
    main()
"""