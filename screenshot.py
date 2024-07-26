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

# Load API key from environment
api_key = os.environ.get('API_survey')

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

def take_screenshots_scroll(driver: webdriver.Chrome, filepath: str = 'screenshot') -> List[str]:
    screenshots = []
    last_height = 0

    while True:
        filename = f'{filepath}_{len(screenshots)}.png'
        driver.save_screenshot(filename)
        screenshots.append(filename)

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

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def answer_survey_choice(api_key: str, output_filename: str, intro_text: str, html_question: str) -> int:
    base64_image = encode_image(output_filename)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    print("Introduction text HERE:", intro_text)

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are answering a survey. The introduction of the survey is as follows: {intro_text}."
                    "You will be given a screenshot of a survey page"
                    "and html code of the question. You have to answer the question as if you are "
                    "a 57 year old man who lives in Nordrhein-Westfalen with 4 others. "
                    "Only return the number of the answer you choose, like '1', '2', '3' or '4', etc."
                )
            },
            {
                "role": "user",
                "content": [
                    {
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question. Only return the number of the answer you choose, like '1', '2', '3' or '4', etc..."
                },
                {
                    "type": "image_url",
                    "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]
    }
      ]
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    print(response.json())
    return int(response.json()["choices"][0]["message"]["content"])

def answer_survey_other(api_key: str, output_filename: str, html_question: str) -> str:
    base64_image = encode_image(output_filename)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are answering a survey. You will be given a screenshot of a survey question"
                    "and html code of the question. You have to answer the question as if you are "
                    "a 57 year old man who lives in Nordrhein-Westfalen with 4 others. "
                    "Only return your answer and nothing else."
                )
            },
            {
                "role": "user",
                "content": [
                    {
                    "type": "text",
                    "text": f"{html_question} \n\n Answer this question as if you were the respondent. Only return your answer."
                },
                {
                    "type": "image_url",
                    "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]
        }
        ]
      }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return response.json()["choices"][0]["message"]["content"]

# function to check if an image is part of the introduction or a new question in the survey
def check_image_type(api_key: str, output_filename: str) -> str:
    base64_image = encode_image(output_filename)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are good at interpreting screenshots for the stage of a survey, whether\
                    the screenshot is part of the introduction or if it is a new question. You will be given a screenshot\
                    of a survey and you will be asked to return if the screenshot is part of the ihtroduction of the survey\
                    or a new question. If the screenshot is part of the introduction, you will be asked to provide the introduction text. \
                    The introduction text is visible in the screenshot. Type it out completely.\
                    You need to answer in JSON format, like in the example below.\
                    {'intro': true, 'intro_text': 'This is the introduction text.'} or \
                    {'intro': false, 'intro_text': 'None'}"
                },
            {
              "role": "user",
              "content": [
                {
                  "type": "text",
                  "text": "Is this part of the introduction or a new question?"
                },
                {
                  "type": "image_url",
                  "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                  }
                }
              ]
            }
          ]
        }
    
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response = json.loads(response.json()["choices"][0]["message"]["content"])
    introduction = response['intro']
    intro_text = response['intro_text']
    return introduction, intro_text

def fill_survey(driver: webdriver.Chrome):
    page_index = 0
    complete_intro_text = ""

    while True:
            screenshots = take_screenshots_scroll(driver)
            output_filename = f'survey_screenshot_{page_index}.png'
            stitch_images_vertically(screenshots, output_filename)

            all_questions = (
                driver.find_elements(By.CLASS_NAME, "cbc_task") +
                driver.find_elements(By.TAG_NAME, 'select') +
                driver.find_elements(By.CLASS_NAME, "question.numeric") +
                driver.find_elements(By.CLASS_NAME, "response_column") +
                driver.find_elements(By.TAG_NAME, 'textarea')
            )

            introduction, intro_text = check_image_type(api_key, output_filename)
            print(f"Introduction: {introduction}")
            print(f"Introduction text: {intro_text}")

            # if the screenshot is part of the introduction, add the introduction text to the complete_intro_text
            if introduction:
                complete_intro_text += intro_text

            def get_position(element):
                location = element.location
                return location['y'], location['x']

            sorted_elements = sorted(all_questions, key=get_position)
            total_questions = len(all_questions)
            print(f"Total questions: {total_questions}")

            for i in range(total_questions):
                element = sorted_elements[i]

                if element in driver.find_elements(By.CLASS_NAME, "cbc_task"):
                    print("Question type: cbc_task")
                    html_question = element.get_attribute('innerHTML')
                    print("Question:", html_question)
                    answer = answer_survey_choice(api_key, output_filename, complete_intro_text, html_question)
                    print("Answer:", answer)
                    element.find_elements(By.CLASS_NAME, "task_select_button")[answer - 1].click()
                    time.sleep(1)

                elif element in driver.find_elements(By.TAG_NAME, 'select'):
                    html_question = element.get_attribute('outerHTML')
                    answer = answer_survey_choice(api_key, output_filename, html_question)
                    print(html_question, answer)
                    select = Select(element)
                    select.select_by_value(str(answer))
                    time.sleep(1)

                elif element in driver.find_elements(By.CLASS_NAME, "question.numeric"):
                    html_question = element.get_attribute('outerHTML')
                    answer = answer_survey_other(api_key, output_filename, html_question)
                    print(html_question, answer)
                    element.find_element(By.TAG_NAME, "input").send_keys(answer)
                    time.sleep(1)

                elif element in driver.find_elements(By.CLASS_NAME, "response_column"):
                    html_question = element.get_attribute('innerHTML')
                    answer = answer_survey_choice(api_key, output_filename, html_question)
                    print(html_question, answer)
                    element.click()
                    time.sleep(1)

                elif element in driver.find_elements(By.TAG_NAME, 'textarea'):
                    html_question = element.get_attribute('innerHTML')
                    answer = answer_survey_other(api_key, output_filename, html_question)
                    print(html_question, answer)
                    element.send_keys(answer)
                    time.sleep(1)

            next_button = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.ID, "next_button")
            )
            next_button.click()
            time.sleep(1)
            page_index += 1
            print(f"Page {page_index} completed.")

    return screenshots

print(fill_survey(driver))

#base64_image = encode_image('survey_screenshot.png')
#
#headers = {
#  "Content-Type": "application/json",
#  "Authorization": f"Bearer {api_key}"
#}
#
#payload = {
#  "model": "gpt-4o",
#  "messages": [
#    {
#        "role": "system",
#        "content": "You are good at interpreting screenshots for the stage of a survey, whether\
#            the screenshot is part of the introduction or if it is a new question. You will be given a screenshot\
#            of a survey and you will be asked to return if the screenshot is part of the ihtroduction of the survey\
#            or a new question. Answer 'Introduction' if the screenshot is part of the introduction of the survey\
#            and 'Question' if the screenshot is a new question. "
#        },
#    {
#      "role": "user",
#      "content": [
#        {
#          "type": "text",
#          "text": "Is this part of the introduction or a new question?"
#        },
#        {
#          "type": "image_url",
#          "image_url": {
#            "url": f"data:image/jpeg;base64,{base64_image}"
#          }
#        }
#      ]
#    }
#  ]
#}
#
#response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
#answer = response.json()["choices"][0]["message"]["content"]
#print(answer)