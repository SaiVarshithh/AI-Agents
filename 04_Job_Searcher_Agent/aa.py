from selenium import webdriver
from selenium.webdriver.common.by import By
import time

driver = webdriver.Chrome()

driver.get("https://www.indeed.com/jobs?q=python+developer+remote&l=India")

time.sleep(5)

jobs = driver.find_elements(By.CLASS_NAME, "job_seen_beacon")

print("Found jobs:", len(jobs))

for job in jobs[:10]:
    try:
        title = job.find_element(By.CSS_SELECTOR, "span[id^='jobTitle']").text
        company = job.find_element(By.CSS_SELECTOR, "[data-testid='company-name']").text
        location = job.find_element(By.CSS_SELECTOR, "[data-testid='text-location']").text

        print(title, "|", company, "|", location)
    except:
        pass

driver.quit()