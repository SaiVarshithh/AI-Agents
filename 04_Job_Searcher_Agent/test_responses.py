#!/usr/bin/env python3
"""
Test script to inspect responses from job sites.
"""

import json
import os
from playwright.sync_api import sync_playwright

def test_naukri():
    print("Testing Naukri API...")
    url = "https://www.naukri.com/jobapi/v3/search"
    params = {
        "noOfResults": "10",
        "urlType": "search_by_key_loc",
        "searchType": "adv",
        "keyword": "python developer",
        "location": "bangalore",
        "jobAge": "7",
        "src": "jobsearchDesk",
        "sType": "1",
        "aArea": ""
    }
    headers = {
        "Appid": "109",
        "appid": "109",
        "systemid": "jobsearchDesk",
        "SystemId": "jobsearchDesk",
        "systemcountrycode": "IN",
        "gid": "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.naukri.com/",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        # Bootstrap: visit main site
        page.goto("https://www.naukri.com/", wait_until="domcontentloaded")
        input("Solve any captcha and press Enter...")
        # Now test API
        resp = context.request.fetch(url, method="GET", headers=headers, params=params)
        print(f"Status: {resp.status}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        body = resp.text()
        print(f"Body (first 500 chars): {body[:500]}")
        if resp.status == 200 and 'json' in resp.headers.get('content-type', ''):
            try:
                data = resp.json()
                print(f"JSON keys: {list(data.keys()) if isinstance(data, dict) else 'Not dict'}")
            except:
                print("Failed to parse JSON")
        context.close()
        browser.close()

def test_monster():
    print("Testing Monster API...")
    url = "https://www.foundit.in/jobsearch/api/v2/jobs/search"
    params = {
        "query": "python developer",
        "locations": "bangalore",
        "postedDate": "7"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.foundit.in/",
        "Origin": "https://www.foundit.in",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        # Bootstrap: visit main site
        page.goto("https://www.foundit.in/", wait_until="domcontentloaded")
        input("Log in if needed and press Enter...")
        # Now test API
        resp = context.request.fetch(url, method="GET", headers=headers, params=params)
        print(f"Status: {resp.status}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        body = resp.text()
        print(f"Body (first 500 chars): {body[:500]}")
        if resp.status == 200 and 'json' in resp.headers.get('content-type', ''):
            try:
                data = resp.json()
                print(f"JSON keys: {list(data.keys()) if isinstance(data, dict) else 'Not dict'}")
            except:
                print("Failed to parse JSON")
        context.close()
        browser.close()

if __name__ == "__main__":
    print("Choose test:")
    print("1. Naukri")
    print("2. Monster")
    choice = input("Enter 1 or 2: ")
    if choice == "1":
        test_naukri()
    elif choice == "2":
        test_monster()
    else:
        print("Invalid choice")