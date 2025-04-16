# scraper.py (Improved with dynamic tab navigation and unified dataset saving)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pickle
import time
import os
import pandas as pd
from datetime import datetime
import re
from urllib.parse import unquote, urlparse, parse_qs
import json

def navigate_to_tab(driver, tab_name):
    try:
        print(f"🔄 Checking if '{tab_name}' tab is available...")
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        tab_xpath = f"//a[.//span[contains(text(), '{tab_name}')]]"
        tab_elements = driver.find_elements(By.XPATH, tab_xpath)
        if tab_elements:
            print(f"✅ Found '{tab_name}' tab in main navigation. Clicking...")
            driver.execute_script("arguments[0].click();", tab_elements[0])
            time.sleep(5)
            return True
        print(f"⚠️ '{tab_name}' tab not found in main navigation. Checking 'More' menu...")
        more_menu_xpath = "//div[contains(@aria-label, 'More') or contains(@aria-label, 'See more')]"
        more_menus = driver.find_elements(By.XPATH, more_menu_xpath)
        if more_menus:
            driver.execute_script("arguments[0].click();", more_menus[0])
            time.sleep(2)
            tab_elements = driver.find_elements(By.XPATH, tab_xpath)
            if tab_elements:
                print(f"✅ Found '{tab_name}' tab inside 'More'. Clicking...")
                driver.execute_script("arguments[0].click();", tab_elements[0])
                time.sleep(5)
                return True
        print(f"❌ '{tab_name}' tab is NOT available on this page.")
        return False
    except Exception as e:
        print(f"⚠️ Error navigating to '{tab_name}': {e}")
        return False

def extract_page_identifier(url):
    match = re.search(r"facebook\.com/(?:profile\.php\?id=)?([^/&]+)", url)
    return match.group(1) if match else "default"

def scrape_facebook_page(page_url):
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get("https://www.facebook.com/")
    time.sleep(3)

    if os.path.exists("facebook_cookies.pkl"):
        with open("facebook_cookies.pkl", "rb") as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        driver.refresh()
        time.sleep(3)
    else:
        input("Login to Facebook manually and press Enter here...")
        cookies = driver.get_cookies()
        with open("facebook_cookies.pkl", "wb") as f:
            pickle.dump(cookies, f)

    driver.get(page_url)
    time.sleep(5)
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    full_posts = soup.find_all("div", class_="x1n2onr6 x1ja2u2z x1jx94hy x1qpq9i9 xdney7k xu5ydu1 xt3gfkd x9f619 xh8yej3 x6ikm8r x10wlt62 xquyuld")

    scraped_posts = []
    for post in full_posts:
        post_description = post.find_next("div", class_="x1l90r2v x1iorvi4 x1ye3gou xn6708d")
        post_text = post_description.get_text().strip() if post_description else "No Text"

        comments = []
        try:
            comment_section = post.find_next("div", class_="xabvvm4 xeyy32k x1ia1hqs x1a2w583 x6ikm8r x10wlt62")
            if comment_section:
                comment_elements = comment_section.find_all("div", class_="x1lliihq xjkvuk6 x1iorvi4")
                comments = [comment.get_text().strip() for comment in comment_elements]
        except:
            pass

        reactions = {}
        try:
            reaction_divs = post.find_all("div", attrs={"aria-label": True})
            for div in reaction_divs:
                label = div["aria-label"]
                if ":" in label and ("person" in label or "people" in label):
                    reaction_type = label.split(":")[0].strip()
                    count_str = label.split(":")[1].strip().split(" ")[0]
                    if count_str.isdigit():
                        reactions[reaction_type] = int(count_str)
        except:
            pass

        timestamp = "Unknown"
        try:
            time_element = post.find("abbr")
            if time_element and time_element.has_attr("data-utime"):
                timestamp = datetime.fromtimestamp(int(time_element["data-utime"])).isoformat()
        except:
            pass

        scraped_posts.append({
            "Post Content": post_text,
            "Comments": comments,
            "Reactions": reactions,
            "Timestamp": timestamp
        })

    about_text = ""
    if navigate_to_tab(driver, "About"):
        try:
            about_soup = BeautifulSoup(driver.page_source, "html.parser")
            about_section = about_soup.find("div", {"class": "x1iyjqo2 x78zum5 x1n2onr6"})
            if about_section:
                about_text = about_section.get_text(separator=" ", strip=True)
        except Exception as e:
            print(f"⚠️ Error extracting About info: {e}")

    review_data = []
    if navigate_to_tab(driver, "Reviews"):
        try:
            reviews_soup = BeautifulSoup(driver.page_source, "html.parser")
            review_containers = reviews_soup.find_all("div", {"role": "article"})
            for r in review_containers:
                user = r.find("strong")
                text = r.get_text(separator=" ", strip=True)
                if user:
                    review_data.append({"User": user.get_text(strip=True), "Review": text})
        except Exception as e:
            print(f"⚠️ Error extracting Reviews: {e}")

    driver.quit()
    df = pd.DataFrame(scraped_posts)
    os.makedirs("data", exist_ok=True)
    identifier = extract_page_identifier(page_url)
    final_path = f"data/final_scraped_dataset_{identifier}.json"
    final_dataset = {
        "About": about_text,
        "Recommendation": "recommended" if "recommend" in about_text.lower() else "not recommended",
        "Reviews": review_data,
        "Posts": scraped_posts
    }
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(final_dataset, f, indent=4, ensure_ascii=False)
    print(f"✅ Combined dataset saved to {final_path}")

    return df
