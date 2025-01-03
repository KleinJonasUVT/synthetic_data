import time
import os
import base64
import requests
from typing import List
from PIL import Image
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import json
import logging
import pandas as pd

# Logging setup function
def setup_logging():
    """
    Configures and returns a logger for debugging and monitoring the script's actions.
    """
    logger = logging.getLogger(__name__)  # Create a logger instance
    logger.setLevel('DEBUG')  # Set logger level to DEBUG

    # Configure console output for the logger
    console_handler = logging.StreamHandler()  
    console_handler.setLevel('DEBUG')

    # Define log message format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Attach the handler to the logger
    logger.addHandler(console_handler)

    return logger

# Load API key from environment variable
api_key = os.environ.get('API_survey')

# Set up logging
logger = setup_logging()

# Load user data from CSV file
#data = pd.read_csv('user_data.csv', delimiter=';')  # Load data into a pandas DataFrame
#logger.info(f"Data loaded from CSV file")  # Log successful data load
#logger.info(data.head())  # Display first few rows of the data for verification

# Function to capture screenshots while scrolling the page
def take_screenshots_scroll(driver: webdriver.Chrome, filepath: str = 'screenshots/screenshot') -> List[str]:
    """
    Takes screenshots while scrolling through the webpage and returns the list of screenshot file paths.
    """
    screenshots = []  # List to hold screenshot file paths
    last_height = 0  # Initialize last scroll position

    while True:
        filename = f'{filepath}_{len(screenshots)}.png'  # Filename for each screenshot
        driver.save_screenshot(filename)  # Capture screenshot
        screenshots.append(filename)  # Add filename to list
        logger.info(f"Screenshot saved: {filename}")

        driver.execute_script("window.scrollBy(0, window.innerHeight);")  # Scroll the page
        time.sleep(2)  # Wait for scroll to complete

        new_height = driver.execute_script("return window.pageYOffset")  # Get new scroll position
        if new_height == last_height:  # Stop if scroll position hasn't changed
            break
        last_height = new_height

    return screenshots

# Function to stitch images vertically into one image
def stitch_images_vertically(images: List[str], output_filename: str = 'stitched.png'):
    """
    Stitches the provided images vertically and saves the resulting image.
    """
    imgs = [Image.open(x) for x in images]  # Load images
    widths, heights = zip(*(i.size for i in imgs))  # Get dimensions of images

    total_height = sum(heights)  # Calculate total height of the stitched image
    max_width = max(widths)  # Calculate max width of the images
    stitched_image = Image.new('RGB', (max_width, total_height))  # Create a blank image canvas

    y_offset = 0  # Initialize vertical offset
    for img in imgs:
        stitched_image.paste(img, (0, y_offset))  # Paste each image in order
        y_offset += img.height  # Update offset for next image

    stitched_image.save(output_filename)  # Save stitched image
    logger.info(f"Stitched image saved: {output_filename}")

# Function to encode an image to base64
def encode_image(image_path: str) -> str:
    """
    Encodes the image at the given path to a base64 string.
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')  # Return base64 encoded image

# Function to handle answering multiple-choice questions via API
def answer_survey_choice(api_key: str, messages) -> int:
    """
    Sends the survey question to the OpenAI API and returns a choice number (int) for multiple-choice questions.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",  # GPT-4 model used for responses
        "messages": messages,
        "top_p": 0.5,
        "temperature": 0.5
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return int(response.json()["choices"][0]["message"]["content"])  # Return choice as integer

# Function to handle answering open-ended questions via API
def answer_survey_other(api_key: str, messages) -> str:
    """
    Sends the survey question to the OpenAI API and returns a text response for open-ended questions.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",  # GPT-4 model used for responses
        "messages": messages,
        "top_p": 0.5,
        "temperature": 0.5
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return response.json()["choices"][0]["message"]["content"]  # Return the text content

# Function to summarize survey answers using OpenAI API
def summarize_answer(api_key, html_question, answer):
    """
    Summarizes the provided answer to the survey question using the OpenAI API.
    """
    client = OpenAI(api_key=api_key)  # Initialize OpenAI client

    response = client.chat.completions.create(
      model="gpt-4o-mini",
      messages=[
        {"role": "system", "content": "You are a helpful assistant that summarizes the answer given to a survey question. \
          You will be given the html code of the question and the answer given by the respondent. You have to summarize the answer."},
        {"role": "user", "content": f"{html_question} \n\n I answered this question with the following answer: {answer}"},
      ]
    )
    logger.info(f"Answer summary: {response.choices[0].message.content}")
    return response.choices[0].message.content  # Return summarized answer

# Main function to fill the survey for a given user
def fill_survey(driver: webdriver.Chrome):
    """
    Automates the process of filling out a survey for a user based on their profile and OpenAI-generated responses.
    """
    page_index = 0  # Track the survey page
    
    # Define the base system message for OpenAI API responses
    messages = [
            {
                "role": "system",
                "content": (
                    f"""Process and answer a question provided in the form of HTML code by taking on a persona with specified characteristics. Only return your answer and nothing else.

- Assume a persona with the following attributes: age between 18 and 80, a certain gender, and occupation. Use these attributes to inform your responses.
- If the question is multiple-choice, only return the number of your selected answer, such as '1', '2', '3', etc.
- If it is a text question, provide the text you would write as a response considering the persona.
- Answer only the HTML-based question, ignoring any other content.

# Steps

1. **Read the HTML Question**: Carefully analyze the HTML code provided to identify the question.
2. **Determine Question Type**: Check if it's a multiple-choice or text-based question.
3. **Respond with Persona**:
   - Assume a persona with defined attributes (e.g., age, gender, occupation).
   - For multiple-choice, return only the number of choice.
   - For text-based, write a concise text response influenced by the persona.

# Output Format

- Return the answer exclusively; for multiple-choice, provide only the number, and for text questions, a short text response reflecting the persona.
- Do not include any other explanations or content beyond the direct answer to the HTML question provided.

# Notes

- Maintain focus on the HTML-based question, disregarding any other data that may appear in the form.
- Use the persona to influence, but not dominate, the response. Ensure your response format aligns with the question type."""
                )
            }
      ]

    # Loop through survey pages and answer questions
    while True:
      content = []
      screenshots = take_screenshots_scroll(driver)  # Take scrolling screenshots of the survey page
      output_filename = f'stitched/survey_screenshot_{page_index}.png'
      stitch_images_vertically(screenshots, output_filename)  # Stitch screenshots into one image

      # Gather all questions on the page by finding elements by their respective classes and tags
      all_questions = (
          driver.find_elements(By.CLASS_NAME, "cbc_task") +
          driver.find_elements(By.TAG_NAME, 'select') +
          driver.find_elements(By.CLASS_NAME, "question.numeric") +
          driver.find_elements(By.CLASS_NAME, "response_column") +
          driver.find_elements(By.TAG_NAME, 'textarea')
      )

      base64_image = encode_image(output_filename)  # Encode the stitched image into base64
      logger.info(f"Image encoded to base64")
      content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                    })
      logger.info(f"Screenshot added to API messages")

      def get_position(element):
          """
          Helper function to get the screen position of an element.
          """
          location = element.location
          return location['y'], location['x']

      sorted_elements = sorted(all_questions, key=get_position)  # Sort questions based on their position on the page
      total_questions = len(all_questions)  # Count number of questions
      logger.info(f"Total questions found: {total_questions}")

      if total_questions == 0:
            # If no questions (e.g., an introductory page), just add the screenshot to messages
            messages.append({
                "role": "user",
                "content": content
            })
            logger.info(f"Screenshot added to messages, no questions found, moving to next page")

      else:
        # Loop through each question found on the page
        for i in range(total_questions):
            element = sorted_elements[i]

            # Check for specific question types and answer accordingly
            if element in driver.find_elements(By.CLASS_NAME, "cbc_task"):
                logger.info(f"Question type: cbc_task")  # Multiple choice task
                html_question = element.get_attribute('innerHTML')
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                  })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                answer = answer_survey_choice(api_key, messages)  # Get answer from OpenAI API
                logger.info(f"Answer: {answer}")
                messages = messages[:-1]  # Remove the question from the messages
                logger.info(f"Removing html question from message thread")
                content = []  # Reset content list
                answer_summary = summarize_answer(api_key, html_question, answer)  # Summarize the answer
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.find_elements(By.CLASS_NAME, "task_select_button")[answer - 1].click()  # Click the chosen answer in the browser
                logger.info(f"Answer selected in chrome browser")
                time.sleep(1)

            # Handle select dropdowns
            elif element in driver.find_elements(By.TAG_NAME, 'select'):
                logger.info(f"Question type: select")
                html_question = element.get_attribute('outerHTML')
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                answer = answer_survey_choice(api_key, messages)  # Get answer from OpenAI API
                logger.info(f"Answer: {answer}")
                messages = messages[:-1]  # Remove the question from the messages
                logger.info(f"Removing html question from message thread")
                content = []  # Reset content list
                answer_summary = summarize_answer(api_key, html_question, answer)  # Summarize the answer
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                select = Select(element)  # Select the dropdown option in the browser
                select.select_by_value(str(answer))
                logger.info(f"Answer selected in chrome browser")
                time.sleep(1)

            # Handle numeric input fields
            elif element in driver.find_elements(By.CLASS_NAME, "question.numeric"):
                logger.info(f"Question type: question numeric")
                html_question = element.get_attribute('outerHTML')
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                answer = answer_survey_other(api_key, messages)  # Get answer from OpenAI API
                logger.info(f"Answer: {answer}")
                messages = messages[:-1]  # Remove the question from the messages
                logger.info(f"Removing html question from message thread")
                content = []  # Reset content list
                answer_summary = summarize_answer(api_key, html_question, answer)  # Summarize the answer
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.find_element(By.TAG_NAME, "input").send_keys(answer)  # Enter the answer into the input field in the browser
                logger.info(f"Answer inputted in chrome browser")
                time.sleep(1)

            # Handle response columns (likely used for multi-select or matrix questions)
            elif element in driver.find_elements(By.CLASS_NAME, "response_column"):
                logger.info(f"Question type: response_column")
                html_question = element.get_attribute('innerHTML')
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                answer = answer_survey_choice(api_key, messages)  # Get answer from OpenAI API
                logger.info(f"Answer: {answer}")
                messages = messages[:-1]  # Remove the question from the messages
                logger.info(f"Removing html question from message thread")
                content = []  # Reset content list
                answer_summary = summarize_answer(api_key, html_question, answer)  # Summarize the answer
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.click()  # Select the answer in the browser
                logger.info(f"Answer selected in chrome browser")
                time.sleep(1)

            # Handle text areas (open text responses)
            elif element in driver.find_elements(By.TAG_NAME, 'textarea'):
                logger.info(f"Question type: textarea")
                html_question = element.get_attribute('innerHTML')
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                answer = answer_survey_other(api_key, messages)  # Get answer from OpenAI API
                logger.info(f"Answer: {answer}")
                messages = messages[:-1]  # Remove the question from the messages
                logger.info(f"Removing html question from message thread")
                content = []  # Reset content list
                answer_summary = summarize_answer(api_key, html_question, answer)  # Summarize the answer
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.send_keys(answer)  # Enter the text response into the text area
                logger.info(f"Answer inputted in chrome browser")
                time.sleep(1)

      # Save the messages to a JSON file for later review
      with open(f'messages.json', 'w') as f:
          json.dump(messages, f)

      # Look for and click the "Next" button to move to the next survey page
      try:
        next_button = WebDriverWait(driver, 10).until(
            lambda d: d.find_element(By.ID, "next_button")
        )
        next_button.click()
      except:
        logger.error(f"Next button not found on page {page_index}.")  # Log an error if the button is not found
        break
      time.sleep(1)
      page_index += 1  # Increment page index
      logger.info(f"Page {page_index} completed")

    return screenshots

# Loop through each row (user) in the loaded CSV data and fill the survey
number_of_respondents = 100
for i in range(number_of_respondents):
    # Set up Chrome WebDriver options
    chrome_options = Options()

    # Make the browser headless
    chrome_options.add_argument("--headless")

    # Use WebDriver Manager to ensure the latest ChromeDriver is installed and used
    service = Service(ChromeDriverManager().install())

    # Initialize Chrome WebDriver
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Open the survey URL
    url = 'https://sustainabilityde.sawtoothsoftware.com/'
    driver.get(url)
    time.sleep(3)  # Wait for the page to load

    print(f"Starting surver for user {i}")
    # Fill out the survey for this user
    fill_survey(driver)

    # Close the browser after completing the survey
    driver.quit()
    logger.info(f"Survey completed for user {i + 1}")
    logger.info(f"Waiting 3 seconds before starting the next survey")
    time.sleep(3)
