from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from IPython.display import clear_output
from typing import Union
from time import sleep
import json
import numpy as np
import os
import pandas as pd
import pickle as pkl

class staleness_of(object):

    def __init__(self, element):
        self.element = element

    def __call__(self, ignored):
        try:
            # Calling any method forces a staleness check
            self.element.is_enabled()
            return False
        except StaleElementReferenceException:
            return True

class AdvancedDriver(WebDriver):

    @staticmethod
    def load_cookies(cookie_path: str) -> list[dict]:
        """
        Loading cookies from a file and returning a list of cookie-dicts.
        """
        with open(cookie_path, 'rt') as f:
            return json.load(f)
    
    @staticmethod
    def yandex_element_has_track_title(element: WebElement) -> bool:
        l = element.find_elements('xpath', './/a[@class="d-track__title deco-link deco-link_stronger"]')
        l += element.find_elements('xpath', './/span[@class="d-track__title deco-link_stronger deco-typo"]')
        return len(l) > 0
    
    @staticmethod
    def get_track_params_yandex(element: WebElement) -> list[int, str, str]:
        n = int(element.get_attribute('data-id'))
        track_name = element.find_elements('xpath', './/a[@class="d-track__title deco-link deco-link_stronger"]')
        track_name += element.find_elements('xpath', './/span[@class="d-track__title deco-link_stronger deco-typo"]')
        track_name = track_name[0].text.strip()
        artist_list = element.find_elements('xpath', './/span[@class="d-track__artists"]/a[@class="deco-link deco-link_muted"]')
        artists = "; ".join([a.get_attribute("title") for a in artist_list])
        return [n, artists, track_name]

    @staticmethod
    def stale_elements_only(elements: list[WebElement]) -> list[WebElement]:
        filtered_elements = []
        for el in elements:
            try:
                el.is_enabled()
                filtered_elements.append(el)
            except StaleElementReferenceException:
                continue
        return filtered_elements
    
    def authorise(driver, url: str, cookie_path: str) -> None:
        """
        Opening a url and authorising on it.
        """
        driver.get(url)
        for cookie_dict in driver.load_cookies(cookie_path):
            driver.add_cookie(cookie_dict)
        
    def get_element_with_wait(
        driver, value: str, element_index: int=0,
        sleeptime: int=0, max_wait: int=15, by: str='xpath',
        one_element: bool=True
    ) -> Union[WebElement, list[WebElement]]:
        """
        Returns the element with waiting for its appearance.
        """
        sleep(sleeptime)
        WebDriverWait(driver, max_wait).until(
            expected_conditions.presence_of_element_located((by, value))
        )
        elements = driver.find_elements(by, value)
        return elements[element_index] if one_element else elements
            
    
    def parse_yandex_tracklist(driver) -> pd.DataFrame:
        elements = driver.get_element_with_wait(
            '//div[@class="d-track typo-track d-track_inline-meta d-track__sidebar d-track_in-lib"]',
            sleeptime=1, one_element=False
        )
        elements = list(filter(driver.yandex_element_has_track_title, elements))
        tracklist_df = pd.DataFrame(
            list(map(driver.get_track_params_yandex, elements)),
            columns=['number', 'artists', 'title']
        )
        element_prev = elements[0]
        while element_prev != elements[-1]:
            element_prev = elements[-1]
            scroll_origin = ScrollOrigin.from_element(element_prev)
            ActionChains(driver)\
                .scroll_from_origin(scroll_origin, 0, 300)\
                .perform()
            sleep(2)
            elements = driver.get_element_with_wait(
                '//div[@class="d-track typo-track d-track_inline-meta d-track__sidebar d-track_in-lib"]',
                sleeptime=1, one_element=False
            )
            elements = list(filter(driver.yandex_element_has_track_title, elements))
            new_tracklist_df = pd.DataFrame(
                list(map(driver.get_track_params_yandex, elements)),
                columns=['number', 'artists', 'title']
            )
            tracklist_df = pd.concat([tracklist_df, new_tracklist_df]).drop_duplicates().reset_index(drop=True)
        tracklist_df.to_feather(driver.yandex_tracklist_path)
        return tracklist_df
        

    def get_yandex_tracklist(driver, save_path: str="sample_data/yandex_tracklist.feather") -> None:
        if os.path.exists(save_path):
            driver.yandex_tracklist = pd.read_feather(save_path)
        else:
            driver.yandex_tracklist_path = save_path
            tracklist_df = driver.parse_yandex_tracklist()
            driver.yandex_tracklist = tracklist_df
    
    def get_yandex_current_track(driver) -> int:
        sleep(0.3)
        track_title = None
        driver.get_element_with_wait('//div[@class="track__name-innerwrap"]', max_wait=10)
        try:
            for i in range(7):
                track_titles = driver.find_elements('xpath', '//a[@class="d-link deco-link track__title"]')
                track_titles = driver.stale_elements_only(track_titles)
                if len(track_titles) != 1:
                    sleep(0.3)
                    continue
                else:
                    track_title = track_titles[0].get_attribute('title').strip()
                    break
            if track_title is None:
                raise NoSuchElementException
        except StaleElementReferenceException:
            for i in range(7):
                track_titles = driver.find_elements('xpath', '//a[@class="d-link deco-link track__title"]')
                track_titles = driver.stale_elements_only(track_titles)
                if len(track_titles) != 1:
                    sleep(0.3)
                    continue
                else:
                    track_title = track_titles[0].get_attribute('title').strip()
                    break
            if track_title is None:
                raise NoSuchElementException
        except NoSuchElementException: 
            # referring to some tracks that are deleted from the service due to license agreements
            # but still somehow there are in my playlist
            for i in range(7):
                track_titles = driver.find_elements('xpath', '//span[@class="track__title"]')
                track_titles = driver.stale_elements_only(track_titles)
                if len(track_titles) != 1:
                    sleep(0.3)
                    continue
                elif len(track_titles):
                    track_title = track_titles[0].text.strip()
                    break
            if track_title is None:
                raise Exception("Couldn't define the track on the first step")
        while "  " in track_title:
            track_title = track_title.replace("  ", " ") # replace with re further
        print(f"Right now {track_title} is playing, ", end="")
        track_title = track_title.lower()
        track_df = driver.yandex_tracklist[driver.yandex_tracklist.title.str.lower() == track_title]
        if track_df.shape[0] > 1:
            artist_list = driver.find_elements('xpath', '//span[@class="d-artists d-artists__expanded"]/a[@class="d-link deco-link"]')
            artists = None
            for i in range(7):
                try:
                    artist_list = driver.stale_elements_only(artist_list)
                    artists = "; ".join([a.get_attribute("title") for a in artist_list])
                    break
                except StaleElementReferenceException:
                    sleep(0.3)
                    continue
            track_df = track_df.query(f'artists == "{artists}"')
            try:
                assert track_df.shape[0] == 1
            except AssertionError as e:
                print(track_title, artists)
                return driver.previous_track # for situations when the artist has changed after we've read the track title.
            print(f"performed by {artists}.")
        elif track_df.shape[0] == 0:
            raise ValueError(track_title)
        print(f"performed by {track_df.artists.tolist()[0]}.")
        return track_df.number.values[0]
    
    def get_yandex_track_order(driver) -> np.array:
        while True:
            sleep(1)
            driver.get("https://music.yandex.ru/users/avefromrussia/playlists")
            xpath = '//div[@class="playlist playlist_selectable"]'
            element = driver.get_element_with_wait(xpath, sleeptime=3, max_wait=15)
            element.click()
            sleep(2)
            class_name = 'button-play button button_round \
button_action button_size_L button_ico local-icon-theme-white \
sidebar-playlist__play button-play__type_playlist'
            try:
                play = driver.get_element_with_wait(f'//button[@class="{class_name}"]', sleeptime=1, max_wait=5)
            except:
                continue
            play.click()
            sleep(2)
            tracks_played = 0
            current_sample = []
            driver.previous_track = -1
            retries = 0
            while tracks_played < driver.yandex_tracklist.shape[0]:
                clear_output(True)
                print(f"Current sample size is {driver.yandex_sample.shape[0]}.")
                print(f"Current mean of first tracks: {driver.yandex_current_mean}.")
                print(f"While the sample mean actually should be {driver.yandex_true_mean}.")
                print("="* 100, end='\n\n')
                print(f"{tracks_played} has been played so far.")
                                
                current_track = driver.get_yandex_current_track()
                if current_track != driver.previous_track or retries == 5:
                    retries = 0
                    current_sample.append(driver.get_yandex_current_track())
                    driver.find_element(
                        'xpath', 
                        '//div[@class="player-controls__btn deco-player-controls__button player-controls__btn_next"]'
                    ).click()
                    tracks_played += 1
                    sleep(0.7)
                else:
                    retries += 1
                    sleep(0.3)
                    continue
            break
        return np.array([current_sample])

    def yandex_sample(driver, samples_n: int, save_path: str="sample_data/yandex_sample.pkl") -> None:
        driver.yandex_sample_path = save_path
        if os.path.exists(save_path):
            with open(save_path, 'rb') as f:
                driver.yandex_sample = pkl.load(f)
        else:
            driver.yandex_sample = np.array([])
        # clicking on the shuffle button
        driver.get_element_with_wait('//div[@class="d-icon d-icon_shuffle"]', max_wait=3).click() 
        while True:
            try:
                driver.yandex_current_mean = driver.yandex_sample[:, 0].mean()
                current_order = driver.get_yandex_track_order()
                if driver.yandex_sample.shape[0] == 0:
                    driver.yandex_sample = current_order
                driver.yandex_sample = np.vstack((driver.yandex_sample, current_order))
            except KeyboardInterrupt:
                a = input(f'The number of samples is {driver.yandex_sample.shape[0]}. Do you want to interrupt the sampling?')
                if a.lower() == 'yes':
                    with open(save_path, 'wb') as f:
                        pkl.dump(driver.yandex_sample, f)
                    break
            except Exception as e:
                with open(save_path, 'wb') as f:
                    pkl.dump(driver.yandex_sample, f)
                raise e

    def yandex_main(driver, samples_n: int=100000):
        driver.authorise('https://music.yandex.ru', 'cookies/yandex.json')
        sleep(1)
        driver.get('https://music.yandex.ru')

        # clicking on 'Collection' button on the navigation bar
        xpath = '//a[@class="nav-kids__tab nav-kids__link typo-nav typo-nav_contrast" and contains(text(), "Collection")]'
        element = driver.get_element_with_wait(xpath, max_wait=25)
        element.click()
        
        # clicking on the Favorites playlist
        xpath = '//div[@class="playlist playlist_selectable"]'
        element = driver.get_element_with_wait(xpath, sleeptime=3, max_wait=15)
        element.click()

        # saving the tracklist
        driver.get_yandex_tracklist()
        driver.yandex_true_mean = driver.yandex_tracklist.number.mean()

        # sampling
        driver.yandex_sample(samples_n)