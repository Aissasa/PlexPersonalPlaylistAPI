from __future__ import unicode_literals

from builtins import str
import sys
import os
import logging
import requests
import argparse
from datetime import date
from plexapi.server import PlexServer

from CustomPlexConfig import CustomPlexConfig
import PlaylistEditDetectionAndConversion

#global settings

DEFAULT_PLEX_CONFIG = CustomPlexConfig("PlexServerDefaultConfig.json")

DEFAULT_PLEX_URL = DEFAULT_PLEX_CONFIG.get("plex_url")
DEFAULT_PLEX_TOKEN = DEFAULT_PLEX_CONFIG.get("plex_token")
DEFAULT_MUSIC_LIB_SECTION_NAME = DEFAULT_PLEX_CONFIG.get("music_lib_section_name")
DEFAULT_DAYS_MARGIN_FOR_SYNC = DEFAULT_PLEX_CONFIG.get("sync_days_margin") # number of days allowed for us to consider syncing a playlist, 0 means it has to be today
DEFAULT_FORCE_SYNC_ALL_PLAYLISTS = DEFAULT_PLEX_CONFIG.get("force_sync_all_playlists")

DEFAULT_PLAYLIST_DIR = DEFAULT_PLEX_CONFIG.get("nvidia_shield_storage_path") + DEFAULT_PLEX_CONFIG.get("nvidia_shield_playlists_relative_root_path") 

DEFAULT_UNMODIFIED_PLAYLISTS_DIR = DEFAULT_PLAYLIST_DIR + "Latest/"
DEFAULT_CONVERTED_PLAYLISTS_DIR = DEFAULT_PLAYLIST_DIR + "Converted/"

DEFAULT_NVIDIA_SHIELD_MACHINE_ID = DEFAULT_PLEX_CONFIG.get("nvidia_shield_id")
DEFAULT_NVIDIA_SHIELD_STORAGE_ROOT = "/storage/%s/" % DEFAULT_NVIDIA_SHIELD_MACHINE_ID
DEFAULT_NVIDIA_SHIELD_PLAYLIST_DIR = DEFAULT_NVIDIA_SHIELD_STORAGE_ROOT + DEFAULT_PLEX_CONFIG.get("nvidia_shield_playlists_relative_root_path")

DEFAULT_PLEX_INTERNAL_CONVERTED_PLAYLISTS_DIR = DEFAULT_NVIDIA_SHIELD_PLAYLIST_DIR + "Converted/"


# set up logging

filename = os.path.basename(__file__)
filename = filename.split('.')[0]

logger = logging.getLogger(filename)
logger.setLevel(logging.DEBUG)

error_format = logging.Formatter('%(asctime)s:%(name)s:%(funcName)s:%(message)s')
stream_format = logging.Formatter('%(message)s')

file_handler = logging.FileHandler('{}.log'.format(filename))
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(error_format)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(stream_format)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

"""
Used to check if we have any playlists that need to be created, removed or updated on plex.
The criterion for a playlist to be updated is that it has been modified within the time frame we specify with DEFAULT_DAYS_MARGIN_FOR_SYNC.
We can bypass the latter by setting force_sync to true.
"""
def diff_playlists(plex_server, music_lib_section_id, unmodified_playlists_dir, force_sync):
    
    if not os.path.exists(unmodified_playlists_dir) or not os.path.isdir(unmodified_playlists_dir):
        logger.error("%s does not exist or is not a directory!", unmodified_playlists_dir)
        return None, None, None
    
    synced_playlists_names = dict() #playlist name, folder
    list_of_files_and_sub_dirs = os.listdir(unmodified_playlists_dir)    
    for file_or_sub_dir in list_of_files_and_sub_dirs:
        #todoAiza we can do this better, this goes only one level down, we wanna catch all files in the hierarchy if it goes deeper
        file_or_sub_dir_path = os.path.join(unmodified_playlists_dir, file_or_sub_dir)
        if os.path.isfile(file_or_sub_dir_path):
            synced_playlist_name = file_or_sub_dir.split(".")[0]
            synced_playlists_names[synced_playlist_name] = ""
            
        elif os.path.isdir(file_or_sub_dir_path):
            list_of_files_and_sub_dirs_under_sub_dir = os.listdir(file_or_sub_dir_path)
            for sub_dir_file_or_sub_dir in list_of_files_and_sub_dirs_under_sub_dir:
                sub_file_path = os.path.join(file_or_sub_dir_path, sub_dir_file_or_sub_dir)

                if os.path.isfile(sub_file_path):
                    synced_playlist_name = sub_dir_file_or_sub_dir.split(".")[0]
                    synced_playlists_names[synced_playlist_name] = file_or_sub_dir
                else:
                    logger.error("The directories hierarchy is deeper than one level in %s!" % sub_file_path)

    
    if len(synced_playlists_names) == 0:
        logger.error("%s does not contain any playlist files!", unmodified_playlists_dir)
        return None, None, None
    
    plex_music_playlists_names = [x.title for x in plex_server.playlists(playlistType="audio", sectionId=music_lib_section_id)]
    
    #!playlists to remove: in plex but not in the latest playlists folder
    playlists_to_remove = [x for x in plex_music_playlists_names if x not in synced_playlists_names]
    
    #!playlists to create: in the latest playlists folder but not in plex
    playlists_to_create = dict()
    #!playlists to update: in both plex and latest playlists folder
    playlists_to_update = dict()
    
    for playlist_name, playlist_folder in synced_playlists_names.items():
        if playlist_name not in plex_music_playlists_names:
            playlists_to_create[playlist_name] = playlist_folder
        else:
            playlist_path = os.path.join(unmodified_playlists_dir, playlist_folder, playlist_name + ".m3u")
            file_updated_date = date.fromtimestamp(os.path.getmtime(playlist_path))
            time_today = date.today()
            time_since_last_updated = time_today - file_updated_date
            if force_sync or time_since_last_updated.days <= DEFAULT_DAYS_MARGIN_FOR_SYNC:
                playlists_to_update[playlist_name] = playlist_folder
    
    return playlists_to_create, playlists_to_update, playlists_to_remove


def delete_playlists(plex_server, playlists_to_delete):
    
    for playlist in playlists_to_delete:
        playlist_obj = plex_server.playlist(title=playlist)
        if playlist_obj is not None:
            logger.info("Requesting the deletion of playlist: " + playlist)
            playlist_obj.delete()
        else:
            logger.warning("Could not find playlist: %s" % playlist)

      
        
def create_or_update_playlists(plex_server, music_lib_section, playlists, unmodified_playlists_dir, converted_playlists_dir):
    
    for playlist_name, playlist_folder in playlists.items():
        playlist_full_path = os.path.join(unmodified_playlists_dir, playlist_folder, playlist_name + ".m3u").replace("\\","/")
        converted_playlist_full_path = os.path.join(converted_playlists_dir, playlist_folder, playlist_name + ".m3u").replace("\\","/")
        logger.debug("Converting the playlist: " + playlist_full_path + " to: " + converted_playlist_full_path)
        PlaylistEditDetectionAndConversion.convert_playlist_for_plex(playlist_full_path, converted_playlist_full_path)
        
        plex_internal_storage_converted_playlist_full_path = os.path.join(DEFAULT_PLEX_INTERNAL_CONVERTED_PLAYLISTS_DIR, playlist_folder, playlist_name + ".m3u").replace("\\","/")
        logger.info("Requesting the creation of playlist: " + plex_internal_storage_converted_playlist_full_path)
        plex_server.createPlaylist(title=playlist_name, section=music_lib_section, m3ufilepath=plex_internal_storage_converted_playlist_full_path)
        

def parse_args():
    
    # Instantiate the parser
    parser = argparse.ArgumentParser(description="Upload playlists to Plex")
    
    # Add arguments
    parser.add_argument("-u", "--plex_url", type=str, default=DEFAULT_PLEX_URL, help="The Plex URL")
    parser.add_argument("-t", "--plex_token", type=str, default=DEFAULT_PLEX_TOKEN, help="The Plex Token")
    parser.add_argument("-s", "--music_lib_section_name", default=DEFAULT_MUSIC_LIB_SECTION_NAME, type=str, help="The Plex Music Library Section Name")
    parser.add_argument("-d", "--playlists_dir", type=str, default=DEFAULT_PLAYLIST_DIR, help="The Playlists Directory Path")
    parser.add_argument("-f", "--force_sync", action=argparse.BooleanOptionalAction, help="If added, we ignore the log files and just look at the playlists folder")
    
    return parser.parse_args()


def main():
        
    args = parse_args()
    
    plex_url = DEFAULT_PLEX_URL
    if args.plex_url:
        plex_url = args.plex_url
        logger.info("Using Plex URL: " + plex_url)
        
    plex_token = DEFAULT_PLEX_TOKEN
    if args.plex_token:
        plex_token = args.plex_token
        logger.info("Using Plex Token: " + plex_token)
    
    music_lib_section_name = DEFAULT_MUSIC_LIB_SECTION_NAME
    if args.music_lib_section_name:
        music_lib_section_name = args.music_lib_section_name
        logger.info("Using Music Library Section Name: " + music_lib_section_name)
        
    playlists_dir = DEFAULT_PLAYLIST_DIR
    if args.playlists_dir:
        playlists_dir = args.playlists_dir
        logger.info("Using Playlists Directory: " + playlists_dir)
        
    force_sync = DEFAULT_FORCE_SYNC_ALL_PLAYLISTS
    if args.force_sync:
        force_sync = args.force_sync
        logging.info("Using Force Sync All Playlists: " + str(force_sync))

    unmodified_playlists_dir = playlists_dir + "Latest/"
    converted_playlists_dir = playlists_dir + "Converted/"    
    
    sess = requests.Session()
    # Ignore verifying the SSL certificate
    sess.verify = False  # '/path/to/certfile'
    # If verify is set to a path to a directory,
    # the directory must have been processed using the c_rehash utility supplied
    # with OpenSSL.
    if sess.verify is False:
        # Disable the warning that the request is insecure, we know that...
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    plex = PlexServer(plex_url, plex_token, session=sess)
    
    # validate the existence of the music section
    sections = plex.library.sections()
    sections_dict = dict()
    music_lib_section = None
    for section in sections:
        sections_dict[section.key] = section.title
        if section.title == music_lib_section_name:
            assert music_lib_section is None
            music_lib_section = section

    if music_lib_section is None:
        logger.error("Music Library Section Name \"{}\" not found".format(music_lib_section_name))
        sys.exit(1)
        
    playlists_to_create = [] 
    playlists_to_update = [] 
    playlists_to_remove = []
    playlists_to_create, playlists_to_update, playlists_to_remove = diff_playlists(plex, music_lib_section.key, unmodified_playlists_dir, force_sync)
    
    if playlists_to_create is not None:
        logger.info("Creating playlists: {}".format(playlists_to_create))
        create_or_update_playlists(plex, music_lib_section, playlists_to_create, unmodified_playlists_dir, converted_playlists_dir)
    else:
        logger.error("Failed to diff created playlists!")
        
    if playlists_to_remove is not None:
        logger.info("Deleting playlists: {}".format(playlists_to_remove))
        delete_playlists(plex, playlists_to_remove)
    else:
        logger.error("Failed to diff removed playlists!")
    
    if playlists_to_update is not None:
        logger.info("Updating playlists: {}".format(playlists_to_update))
        delete_playlists(plex, playlists_to_update)
        create_or_update_playlists(plex, music_lib_section, playlists_to_update, unmodified_playlists_dir, converted_playlists_dir)
    else:
        logger.error("Failed to diff updated playlists!")
        
        
if __name__ == '__main__':
    main()