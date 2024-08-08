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

def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel('DEBUG')

    console_handler = logging.StreamHandler()
    console_handler.setLevel('DEBUG')

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger

# Load API key from environment
api_key = os.environ.get('API_survey')

# Set up logging
logger = setup_logging()

# Open the csv file with user data
# Load the data from the CSV file
data = pd.read_csv('user_data.csv', delimiter=';')
logger.info(f"Data loaded from CSV file")
# Showing head of the data
logger.info(data.head())

def take_screenshots_scroll(driver: webdriver.Chrome, filepath: str = 'screenshots/screenshot') -> List[str]:
    screenshots = []
    last_height = 0

    while True:
        filename = f'{filepath}_{len(screenshots)}.png'
        driver.save_screenshot(filename)
        screenshots.append(filename)
        logger.info(f"Screenshot saved: {filename}")

        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(2)

        new_height = driver.execute_script("return window.pageYOffset")
        if new_height == last_height:
            break
        last_height = new_height

    return screenshots

def stitch_images_vertically(images: List[str], output_filename: str = 'stitched.png'):
    imgs = [Image.open(x) for x in images]
    widths, heights = zip(*(i.size for i in imgs))

    total_height = sum(heights)
    max_width = max(widths)
    stitched_image = Image.new('RGB', (max_width, total_height))

    y_offset = 0
    for img in imgs:
        stitched_image.paste(img, (0, y_offset))
        y_offset += img.height

    stitched_image.save(output_filename)
    logger.info(f"Stitched image saved: {output_filename}")

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def answer_survey_choice(api_key: str, messages) -> int:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",
        "messages": messages,
        "top_p": 0.5,
        "temperature": 0.5
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return int(response.json()["choices"][0]["message"]["content"])

def answer_survey_other(api_key: str, messages) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",
        "messages": messages,
        "top_p": 0.5,
        "temperature": 0.5
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return response.json()["choices"][0]["message"]["content"]

def summarize_answer(api_key, html_question, answer):
    client = OpenAI(api_key=api_key)
    # summarize the answer given to the survey question with an openai api call
    response = client.chat.completions.create(
      model="gpt-4o-mini",
      messages=[
        {"role": "system", "content": "You are a helpful assistant that summarizes the answer given to a survey question."\
          "You will be given the html code of the question and the answer given by the respondent. "\
          "You have to summarize the answer."},
        {"role": "user", "content": f"{html_question} \n\n I answered this question with the following answer: {answer}"},
      ]
    )
    logger.info(f"Answer summary: {response.choices[0].message.content}")
    return response.choices[0].message.content

def fill_survey(driver: webdriver.Chrome, age, gender, Country_origin, ethnicity, Country, student_text, work_status):
    page_index = 0
    logger.info(f"Starting survey for user with: age {age}, gender {gender}, country of origin {Country_origin}, ethnicity {ethnicity}, country {Country}, student status {student_text}, work status {work_status}")
    messages = [
            {
                "role": "system",
                "content": (
                    f"You are answering a survey. You will be given html code of the question. \
                    You have to answer the question as if you are a {age} year old {gender} \
                    born in {Country_origin} with ethnicity {ethnicity} who lives in {Country}, Nordrhein-Westfalen. \
                    {student_text} and your work status is: {work_status}. So: \
                    - Age: {age} \
                    - Gender: {gender} \
                    - Country of origin: {Country_origin} \
                    - German state: Nordrhein-Westfalen \
                    - Ethnicity: {ethnicity} \
                    - Country: {Country} \
                    - Student: {student_text} \
                    - Work status: {work_status} \
                    Only return your answer and nothing else."
                    "Only return the number of the answer you choose, like '1', '2', '3' or '4', etc."
                )
            }
      ]

    while True:
      content = []
      screenshots = take_screenshots_scroll(driver)
      output_filename = f'stitched/survey_screenshot_{page_index}.png'
      stitch_images_vertically(screenshots, output_filename)

      all_questions = (
          driver.find_elements(By.CLASS_NAME, "cbc_task") +
          driver.find_elements(By.TAG_NAME, 'select') +
          driver.find_elements(By.CLASS_NAME, "question.numeric") +
          driver.find_elements(By.CLASS_NAME, "response_column") +
          driver.find_elements(By.TAG_NAME, 'textarea')
      )

      base64_image = encode_image(output_filename)
      logger.info(f"Image encoded to base64")
      content.append({
                  "type": "image_url",
                  "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                  }
                })
      logger.info(f"Screenshot added to API messages")

      def get_position(element):
          location = element.location
          return location['y'], location['x']

      sorted_elements = sorted(all_questions, key=get_position)
      total_questions = len(all_questions)
      logger.info(f"Total questions found: {total_questions}")

      if total_questions == 0:
            # If no questions(introduction) are found, add only the image to the messages thread
            messages.append({
                "role": "user",
                "content": content
            })
            logger.info(f"Screenshot added to messages, no questions found, moving to next page")

      else:
        for i in range(total_questions):
            element = sorted_elements[i]
            logger.debug(f"Element: {element}")

            if element in driver.find_elements(By.CLASS_NAME, "cbc_task"):
                logger.info(f"Question type: cbc_task")
                html_question = element.get_attribute('innerHTML')
                logger.debug(f"HTML question: {html_question}")
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                  })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                logger.debug(f"Messages: {messages}")
                answer = answer_survey_choice(api_key, messages)
                logger.info(f"Answer: {answer}")
                # remove the last message from the messages list
                messages = messages[:-1]
                logger.info(f"Removing html question from message thread")
                # summarize the answer given to the survey question
                answer_summary = summarize_answer(api_key, html_question, answer)
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.find_elements(By.CLASS_NAME, "task_select_button")[answer - 1].click()
                logger.info(f"Answer selected in chrome browser")
                time.sleep(1)

            elif element in driver.find_elements(By.TAG_NAME, 'select'):
                logger.info(f"Question type: select")
                html_question = element.get_attribute('outerHTML')
                logger.debug(f"HTML question: {html_question}")
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                logger.debug(f"Messages: {messages}")
                answer = answer_survey_choice(api_key, messages)
                logger.info(f"Answer: {answer}")
                # remove the last message from the messages list
                messages = messages[:-1]
                logger.info(f"Removing html question from message thread")
                # summarize the answer given to the survey question
                answer_summary = summarize_answer(api_key, html_question, answer)
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                select = Select(element)
                select.select_by_value(str(answer))
                logger.info(f"Answer selected in chrome browser")
                time.sleep(1)


            elif element in driver.find_elements(By.CLASS_NAME, "question.numeric"):
                logger.info(f"Question type: question numeric")
                html_question = element.get_attribute('outerHTML')
                logger.debug(f"HTML question: {html_question}")
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                logger.debug(f"Messages: {messages}")
                answer = answer_survey_other(api_key, messages)
                logger.info(f"Answer: {answer}")
                # remove the last message from the messages list
                messages = messages[:-1]
                logger.info(f"Removing html question from message thread")
                # summarize the answer given to the survey question
                answer_summary = summarize_answer(api_key, html_question, answer)
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.find_element(By.TAG_NAME, "input").send_keys(answer)
                logger.info(f"Answer inputted in chrome browser")
                time.sleep(1)

            elif element in driver.find_elements(By.CLASS_NAME, "response_column"):
                logger.info(f"Question type: response_column")
                html_question = element.get_attribute('innerHTML')
                logger.debug(f"HTML question: {html_question}")
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                logger.debug(f"Messages: {messages}")
                answer = answer_survey_choice(api_key, messages)
                logger.info(f"Answer: {answer}")
                # remove the last message from the messages list
                messages = messages[:-1]
                logger.info(f"Removing html question from message thread")
                # summarize the answer given to the survey question
                answer_summary = summarize_answer(api_key, html_question, answer)
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.click()
                logger.info(f"Answer selected in chrome browser")
                time.sleep(1)

            elif element in driver.find_elements(By.TAG_NAME, 'textarea'):
                logger.info(f"Question type: textarea")
                html_question = element.get_attribute('innerHTML')
                logger.debug(f"HTML question: {html_question}")
                content.append({
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                })
                messages.append({
                    "role": "user",
                    "content": content
                })
                logger.info(f"HTML question added to messages")
                logger.debug(f"Messages: {messages}")
                answer = answer_survey_other(api_key, messages)
                logger.info(f"Answer: {answer}")
                # remove the last message from the messages list
                messages = messages[:-1]
                logger.info(f"Removing html question from message thread")
                # summarize the answer given to the survey question
                answer_summary = summarize_answer(api_key, html_question, answer)
                messages.append({
                    "role": "assistant",
                    "content": f"{answer_summary}"
                })
                logger.info(f"Answer summary added to message thread")
                element.send_keys(answer)
                logger.info(f"Answer inputted in chrome browser")
                time.sleep(1)

      # add messages to a json file
      with open(f'messages.json', 'w') as f:
          json.dump(messages, f)

      next_button = WebDriverWait(driver, 10).until(
          lambda d: d.find_element(By.ID, "next_button")
      )
      next_button.click()
      time.sleep(1)
      page_index += 1
      logger.info(f"Page {page_index} completed")

    return screenshots

# Iterate over each row in the dataframe
for index, row in data.iterrows():
    # Extract the necessary variables
    age = row['Age']
    gender = row['Sex']
    Country_origin = row['Country_of_birth']
    ethnicity = row['Ethnicity']
    Country = row['Country_of_residence']
    student_status = row['Student_status']
    work_status = row['Employment_status']

    # Translate student status to the required text
    student_text = "You are a student" if student_status == "Yes" else "You are not a student"

    # Set up Chrome options
    chrome_options = Options()

    # Use webdriver-manager to manage ChromeDriver installation
    service = Service(ChromeDriverManager().install())

    # Set up the Chrome WebDriver with the managed service
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Open the survey URL
    url = 'https://sustainabilityde.sawtoothsoftware.com/'
    driver.get(url)
    time.sleep(3)  # Ensure page is fully loaded

    fill_survey(driver, age, gender, Country_origin, ethnicity, Country, student_text, work_status)

    # Close the browser
    driver.quit()