# scraper.py (Improved with dynamic tab navigation and deep scroll scraping)

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
                driver.execute_script("arguments[0].click();", tab_elements[0])
                time.sleep(5)
                return True
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

    # Deep scroll to load more posts
    MAX_SCROLLS = 15
    SCROLL_PAUSE_TIME = 3
    last_height = driver.execute_script("return document.body.scrollHeight")
    for i in range(MAX_SCROLLS):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print(f"✅ Scrolling finished after {i+1} iterations.")
            break
        last_height = new_height

    soup = BeautifulSoup(driver.page_source, "html.parser")
    full_posts = soup.find_all("div", class_="x1n2onr6 x1ja2u2z x1jx94hy x1qpq9i9 xdney7k xu5ydu1 xt3gfkd x9f619 xh8yej3 x6ikm8r x10wlt62 xquyuld")
    recommendation_text = "not available"
    try:
        soup_about = BeautifulSoup(driver.page_source, "html.parser")
        recommendation_container = soup_about.find_all("div", class_="x9f619 x1n2onr6 x1ja2u2z x78zum5 xdt5ytf x193iq5w xeuugli x1r8uery x1iyjqo2 xs83m0k xsyo7zv x16hj40l x10b6aqq x1yrsyyn")
        recommendation_span = None

        for block in recommendation_container:
            span_candidates = block.find_all("span")
            for span in span_candidates:
                text = span.get_text(strip=True)
                if "recommend" in text.lower():
                    recommendation_text = text
                    recommendation_span = span
                    break
            if recommendation_span:
                break

        if recommendation_span:
            print(f"✅ Extracted Recommendation: {recommendation_text}")
        else:
            print("⚠️ No recommendation span found.")
    except Exception as e:
        print(f"⚠️ Error extracting recommendation text: {e}")

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
            time_element = post.find("div", class_="html-span xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs x4k7w5x x1h91t0o x1h9r5lt x1jfb8zj xv2umb2 x1beo9mf xaigb6o x12ejxvf x3igimt xarpa2k xedcshv x1lytzrv x1t2pt76 x7ja8zs x1qrby5j")
            print(f"time_element: {time_element}")
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

    # About info
    about_text = ""
    if navigate_to_tab(driver, "About"):
    # Only scroll and wait if the tab is available
        time.sleep(3)
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)
        
        soup_about = BeautifulSoup(driver.page_source, "html.parser")
        about_data = {}
        try:
            # Extract Address
            address = soup_about.find("div", class_="xzsf02u x6prxxf xvq8zen x126k92a x12nagc")
            print(f"address is: {address}")
            if address:
                about_data["Address"] = address.get_text().strip()

            # Extract Contact Information (Phone Number or URL)
            contact_all = soup_about.find("div", class_="x9f619 x1n2onr6 x1ja2u2z x78zum5 xdt5ytf x193iq5w xeuugli x1r8uery x1iyjqo2 xs83m0k xamitd3 xsyo7zv x16hj40l x10b6aqq x1yrsyyn")
            mobile_all = soup_about.find_next("div", class_="x9f619 x1n2onr6 x1ja2u2z x78zum5 xdt5ytf x193iq5w xeuugli x1r8uery x1iyjqo2 xs83m0k xamitd3 xsyo7zv x16hj40l x10b6aqq x1yrsyyn")
            print(f"mobile_all: {mobile_all}")

            if contact_all:
                contact_element = contact_all.find_next("span", class_="x193iq5w xeuugli x13faqbe x1vvkbs x1xmvt09 x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x xudqn12 x3x7a5m x6prxxf xvq8zen xo1l8bm xzsf02u x1yc453h")
                
                if contact_element:
                    contact_value = contact_element.get_text().strip()
                    print(f"Extracted Contact: {contact_value}")

                    # Check if the extracted value is a URL
                    if "http" in contact_value or contact_element.find("a"):
                        website_url = contact_element.find("a")["href"] if contact_element.find("a") else contact_value

                        # Handle Facebook redirect links
                        if "l.facebook.com/l.php" in website_url:
                            parsed_url = urlparse(website_url)
                            query_params = parse_qs(parsed_url.query)
                            if "u" in query_params:
                                website_url = query_params["u"][0]

                        # Decode URL
                        website_url = unquote(website_url)
                        about_data["Website"] = website_url
                        print(f"✅ Website found and set: {website_url}")

                    # Check if the value is a valid phone number (digits, spaces, dashes, or plus sign)
                    elif re.match(r"^\+?\d[\d\s\-()]*$", contact_value):
                        about_data["Contact"] = contact_value
                        print(f"✅ Contact number found and set: {contact_value}")

                    else:
                        about_data["Address"] = contact_value  # Store as address if it's neither a URL nor a phone number
                        print(f"✅ Address found and set: {contact_value}")
                else:
                    print("❌ No contact information found.")
            else:
                print("❌ No contact section found.")
        except Exception as e:
            print(f"⚠️ Error extracting About information: {e}")
        
        print(f"📌 Extracted 'About' Info: {about_data}")
    else:
        print("Skipping About extraction because 'About' tab is not available.")
        about_data = {}

    # Reviews
    review_data = []
    if navigate_to_tab(driver, "Reviews"):
        time.sleep(3)
        for _ in range(50):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)
        
        def expand_reviews():
            try:
                while True:
                    see_more_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'See More')]")
                    if not see_more_buttons:
                        break
                    for btn in see_more_buttons:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(2)
            except Exception as e:
                print(f"⚠️ Error expanding reviews: {e}")
        
        expand_reviews()
        soup_reviews = BeautifulSoup(driver.page_source, "html.parser")
        
        new_reviews = []
        try:
            review_full = soup_reviews.find_all("div", class_="html-div xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x78zum5 x1n2onr6 xh8yej3")
            for review in review_full:
                user_name_element = review.find_next("strong", class_="html-strong xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs x1s688f")
                user_name = user_name_element.get_text().strip() if user_name_element else "Unknown User"
                review_text_element = review.find_next("span", class_="html-span xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs xzsf02u xngnso2 xo1l8bm x1qb5hxa")
                review_text = review_text_element.get_text().strip() if review_text_element else "No review text"
                new_reviews.append({"User": user_name, "Review": review_text})
        except Exception as e:
            print(f"⚠️ Error extracting reviews: {e}")
        
        all_reviews = new_reviews
        
        print(f"✅ Scraped {len(new_reviews)} new reviews. Total reviews saved: {len(all_reviews)}")
    else:
        print("Skipping Reviews extraction because 'Reviews' tab is not available.")

    # Save combined
    driver.quit()
    os.makedirs("data", exist_ok=True)
    identifier = extract_page_identifier(page_url)
    final_path = f"data/final_scraped_dataset_{identifier}.json"
    final_dataset = {
        "About": about_data,
        "Recommendation": recommendation_text if isinstance(recommendation_text, str) else str(recommendation_text),
        "Reviews": all_reviews,
        "Posts": scraped_posts
    }
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(final_dataset, f, indent=4, ensure_ascii=False)
    print(f"✅ Combined dataset saved to {final_path}")

    return pd.DataFrame(scraped_posts)
