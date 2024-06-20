import time
import os
from openai import OpenAI
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from typing import List
from PIL import Image
import base64
import requests
from selenium.webdriver.common.by import By

api_key = os.environ.get('API_survey')

# Webdriver setup
chrome_options = webdriver.ChromeOptions()

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

#url = 'https://sustainabilityde.sawtoothsoftware.com/cgi-bin/ciwweb.pl?hid_s=Av8AAFIGp4ZPTWJ7lXqr_j4vY90vAAAAYiqQt3d1VUmjTprSDx9X5X43kLd3dVVPokuY0g8dW_FDNovDGhImFPIb9IgNA1Px'
url = 'https://sustainabilityde.sawtoothsoftware.com/'
#url = 'https://cellospritz.sawtoothsoftware.com/'

driver.get(url)

# Add a very brief sleep to ensure that it is fully loaded
time.sleep(3)

def take_screenshots_scroll(driver: webdriver.Chrome(), filepath: str='screenshot') -> List[str]:
    last_height = 0
    screenshots = []
    
    while True:
        # Take a screenshot
        filename = f'{filepath}_{len(screenshots)}.png'
        driver.save_screenshot(filename)
        screenshots.append(filename)

        # Scroll down by one viewport height and wait for the scroll to load
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(2)  # Wait for scroll to finish

        # Calculate new scroll height and compare with last scroll height
        new_height = driver.execute_script("return window.pageYOffset")
        if new_height == last_height:
            # If heights are the same, it is the end of the page
            break
        last_height = new_height
    return screenshots

def stitch_images_vertically(images: List[str], output_filename: str='stitched.png'):
    images = [Image.open(x) for x in images]
    widths, heights = zip(*(i.size for i in images))

    total_height = sum(heights)
    max_width = max(widths)

    stitched_image = Image.new('RGB', (max_width, total_height))

    y_offset = 0
    for im in images:
        stitched_image.paste(im, (0, y_offset))
        y_offset += im.height

    stitched_image.save(output_filename)

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

# Make a function (bot) that will answer the survey with an image input and return the answer
def answer_survey_choice(output_filename, html_question):

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
            "content": f"You are answering a survey. You will be given a screenshot of a survey \
                and html code of the question. You have to answer the question as if you are a 57 year old men who lives in Nordrhein-Westfalen with 4 others.\
                Only return the number of the answer you choose, like '1', '2', '3' or '4', etc..."
            },
        {
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": f"{html_question} \n\n Answer this question, Only return the number of the answer you choose, like '1', '2', '3' or '4', etc..."
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
    answer = response.json()["choices"][0]["message"]["content"]
    return int(answer)

def answer_survey_other(output_filename, html_question):

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
            "content": f"You are answering a survey. You will be given a screenshot of a survey \
                and html code of the question. You have to answer the question as if you are a 57 year old men who lives in Nordrhein-Westfalen with 4 others.\
                Only return your answer and nothing else."
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
    answer = response.json()["choices"][0]["message"]["content"]
    return answer

def fill_survey(driver):
    page_index = 0
    while True:
            try:
                screenshots = take_screenshots_scroll(driver)
                output_filename = f'survey_screenshot_{page_index}.png'
                stitch_images_vertically(screenshots, output_filename)

                # find all questions
                all_questions = []
                choices = []
                choices += driver.find_elements(By.CLASS_NAME, "cbc_task")
                all_questions += choices
                dropdowns = []
                dropdowns += driver.find_elements(By.TAG_NAME, 'select')
                all_questions += dropdowns
                numeric_inputs = []
                numeric_inputs += driver.find_elements(By.CLASS_NAME, "question.numeric")
                all_questions += numeric_inputs
                radio_buttons = []
                radio_buttons += driver.find_elements(By.CLASS_NAME, "response_column")
                all_questions += radio_buttons
                text_areas = []
                text_areas += driver.find_elements(By.TAG_NAME, 'textarea')
                all_questions += text_areas

                def get_position(element):
                    location = element.location
                    return location['y'], location['x']

                # Sort the elements based on their positions on the page
                sorted_elements = sorted(all_questions, key=get_position)

                print(all_questions)
                print(sorted_elements)

                # identify the total number of questions
                total_questions = len(all_questions)
                print(f"Total questions: {total_questions}")

                # Answer all questions in the screenshot in a for loop
                for i in range(total_questions):
                    
                    # Click on each choice question
                    if sorted_elements[i] in choices:
                        html_question = sorted_elements[i].get_attribute('innerHTML')
                        answer = answer_survey_choice(output_filename, html_question)
                        print(html_question)
                        print(f"Answer: {answer}")
                        sorted_elements[i].find_elements(By.CLASS_NAME, "task_select_button")[answer - 1].click()
                        time.sleep(1)

                    # Select value in dropdowns
                    elif sorted_elements[i] in dropdowns:
                        html_question = sorted_elements[i].get_attribute('outerHTML')
                        answer = answer_survey_choice(output_filename, html_question)
                        print(html_question)
                        print(answer)
                        select = Select(sorted_elements[i])
                        select.select_by_value(str(answer))
                        time.sleep(1)

                    # Enter value in numeric inputs
                    elif sorted_elements[i] in numeric_inputs:
                        html_question = sorted_elements[i].get_attribute('outerHTML')
                        answer = answer_survey_other(output_filename, html_question)
                        print(html_question)
                        print(answer)
                        sorted_elements[i].find_element(By.TAG_NAME, "input").send_keys(answer)
                        time.sleep(1)

                    # Click on radio buttons
                    elif sorted_elements[i] in radio_buttons:
                        html_question = sorted_elements[i].get_attribute('innerHTML')
                        answer = answer_survey_choice(output_filename, html_question)
                        print(html_question)
                        print(answer)
                        sorted_elements[i].click()
                        time.sleep(1)

                    # Enter text in text areas
                    elif sorted_elements[i] in text_areas:
                        html_question = sorted_elements[i].get_attribute('innerHTML')
                        answer = answer_survey_other(output_filename, html_question)
                        print(html_question)
                        print(answer)
                        sorted_elements[i].send_keys(answer)
                        time.sleep(1)

                # Attempt to find the "Next" button and click it
                next_button = WebDriverWait(driver, 10).until(
                    lambda d: d.find_element(By.ID, "next_button")
                )
                next_button.click()
                time.sleep(1)

                # increment page index
                page_index += 1
                print(f"Page {page_index} completed.")

            except Exception as e:
                # If the button is not found, break from the loop
                print(e)
                print("Next button not found. Ending the loop.")
                break
    return screenshots

print(fill_survey(driver))

# Function to encode the image
#def encode_image(image_path):
#  with open(image_path, "rb") as image_file:
#    return base64.b64encode(image_file.read()).decode('utf-8')
#
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