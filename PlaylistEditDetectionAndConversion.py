import errno
import os
import glob
import re
import logging
from CustomPlexConfig import CustomPlexConfig

FREE_FILE_SYNC_LOGS_DIR = "D:/Music/MusicBee/Playlists/Logs"

DEFAULT_PLEX_CONFIG = CustomPlexConfig("PlexServerDefaultConfig.json")

DEFAULT_NVIDIA_SHIELD_MACHINE_ID = DEFAULT_PLEX_CONFIG.get("nvidia_shield_id")
DEFAULT_NVIDIA_SHIELD_STORAGE_ROOT = "/storage/%s/" % DEFAULT_NVIDIA_SHIELD_MACHINE_ID
DEFAULT_NVIDIA_SHIELD_MUSIC_DIR = DEFAULT_NVIDIA_SHIELD_STORAGE_ROOT + DEFAULT_PLEX_CONFIG.get("nvidia_shield_music_relative_root_path")
DEFAULT_NVIDIA_SHIELD_PLAYLIST_DIR = DEFAULT_NVIDIA_SHIELD_STORAGE_ROOT + DEFAULT_PLEX_CONFIG.get("nvidia_shield_playlists_relative_root_path")

DEFAULT_PLAYLIST_DIR = DEFAULT_PLEX_CONFIG.get("nvidia_shield_storage_path") + DEFAULT_PLEX_CONFIG.get("nvidia_shield_playlists_relative_root_path") 
DEFAULT_UNMODIFIED_PLAYLISTS_DIR = DEFAULT_PLAYLIST_DIR + "Latest/"
DEFAULT_CONVERTED_PLAYLISTS_DIR = DEFAULT_PLAYLIST_DIR + "Converted/"

CREATED_PLAYLIST_KEYWORD = "Creating file"
UPDATED_PLAYLIST_KEYWORD = "Updating file"
MOVED_PLAYLIST_KEYWORD = "Moving file"
DELETED_PLAYLIST_KEYWORD = "Deleting file"

EXPECTED_PLAYLIST_EXTENSION = "m3u"
REGEX_PATTERN_EACH_IN_A_GROUP = "(\.\.\/\.\.\/)(.+)(\/)(.+)(\/)(.+)(\/)(.+)"
#REGEX_PATTERN_REPLACE_WITH_INTERNAL_DRIVE_PATH = "(\.\.\/\.\.\/)"
REGEX_PATTERN_REPLACE_WITH_INTERNAL_DRIVE_PATH = "(.+)Library"

"""
Creates directories specified by a path.
If the directory does not exist, it is created. If the directory already exists, nothing happens.
"""
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def get_newest_log_file(log_dir = FREE_FILE_SYNC_LOGS_DIR) -> str:
    if not os.path.exists(log_dir) or not os.path.isdir(log_dir):
        logging.error("%s does not exist or is not a directory!", log_dir)
        return None
    
    directory = os.listdir(log_dir)
    if len(directory) == 0:
        logging.error("%s does not contain any log files!", log_dir)
        return None
    
    list_of_files = glob.glob(os.path.join(log_dir, '*.html'))
    assert len(list_of_files) > 0, "No log files found in %s" % log_dir
    newest_file = max(list_of_files, key=os.path.getctime)
    assert newest_file is not None
    
    return newest_file

"""
Extracts playlist name from the log generated by freefilesync.
Not needed anymore.
"""
def extract_playlist_name_from_line(line) -> str:
    #result = re.search("Latest\\\\*(.+)\.m3u", line) #? if we use this, we need to use the first index in the group for the name
    #result = re.search("quot;(.+\\\\)*(.+)\.m3u", line) #? this does not account for files that are not m3u
    result = re.search("quot;(.+\\\\)*(.+)\.(.+?)\&quot", line)
    if not result or result.lastindex < 2:
        logging.error("Failed to extract playlist name from line: %s", line)
        return None
    
    if result.lastindex >= 3 and result.group(3) != EXPECTED_PLAYLIST_EXTENSION:
        logging.warning("We have files that are not %s: %s%s.%s", EXPECTED_PLAYLIST_EXTENSION, result.group(1), result.group(2), result.group(3))
        return ""
    
    return result.group(2)

"""
Extracts playlists changes from the log generated by freefilesync.
Not needed anymore.
"""
def collect_playlists_from_log_file(log_file = get_newest_log_file()) -> tuple[list[str], list[str], list[str]]:
    if not os.path.exists(log_file) or not os.path.isfile(log_file):
        logging.error("%s does not exist or is not a file!", log_file)
        return None, None, None
    
    with open(log_file, mode="r", encoding="utf-8") as f:
        lines = f.readlines()
        created_playlists = set()
        updated_playlists = set()
        removed_playlists = set()
        for line in lines:
            if line.find(CREATED_PLAYLIST_KEYWORD) > -1:
                created_playlist = extract_playlist_name_from_line(line)
                assert created_playlist is not None
                if created_playlist in created_playlists:
                    logging.warning("%s has already been added to the created playslists!", created_playlist)
                elif created_playlist != "":
                    created_playlists.add(created_playlist)
                
            elif line.find(UPDATED_PLAYLIST_KEYWORD) > -1:
                updated_playlist = extract_playlist_name_from_line(line)
                assert updated_playlist is not None
                if updated_playlist in updated_playlists:
                    logging.warning("%s has already been added to the updated playslists!", updated_playlist)
                elif updated_playlist != "":
                    updated_playlists.add(updated_playlist)
                
            elif line.find(MOVED_PLAYLIST_KEYWORD) > -1 or line.find(DELETED_PLAYLIST_KEYWORD) > -1:
                removed_playlist = extract_playlist_name_from_line(line)
                assert removed_playlist is not None
                if removed_playlist in removed_playlists:
                    logging.warning("%s has already been added to the removed playslists!", removed_playlist)
                elif removed_playlist != "":
                    removed_playlists.add(removed_playlist)
        
        return created_playlists, updated_playlists, removed_playlists

"""
Converts playlists that are created locally in windows to a fomat that works for plex on nvidia shield.
"""
def convert_playlist_for_plex(playlist_file_path, target_file_path):
    if not os.path.exists(playlist_file_path) or not os.path.isfile(playlist_file_path):
        logging.error("%s does not exist or is not a file!", playlist_file_path)
        return None
    
    converted_lines = []
    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
    with open(target_file_path, mode="w", encoding="utf-8") as target_file:
        with open(playlist_file_path, mode="r", encoding="utf-8") as playlist_file:
            lines = playlist_file.readlines()
            for line in lines:
                converted_line = re.sub(REGEX_PATTERN_REPLACE_WITH_INTERNAL_DRIVE_PATH, DEFAULT_NVIDIA_SHIELD_MUSIC_DIR + "Library", line)
                converted_lines.append(converted_line)         
        target_file.writelines(converted_lines)
        
    logging.debug("Converted %s to %s", playlist_file_path, target_file_path)

"""
Testing ground
"""

def main():
    print("--------- Newest log file test --------------")
    newest_file = get_newest_log_file()
    print(newest_file)
    
    print("")
    print("--------- One line Playlist Extraction test --------------")
    log_test_line = "<td>Updating file &quot;O:\Media\Music\Playlists\Latest\Best of the Best.m3u&quot;</td>"
    playlist_name = extract_playlist_name_from_line(log_test_line)
    print(playlist_name + "was extracted from %s" % log_test_line)
    
    print("")
    print("--------- Log file Playlists Extraction test --------------")
    created_playlists = set()
    updated_playlists = set()
    removed_playlists = set()
    
    creation_log_file = "D:\Music\MusicBee\Playlists\Logs\[Last session] 2022-12-27 003816.104.html"
    update_log_file = "D:\Music\MusicBee\Playlists\Logs\[Last session] 2022-12-26 194004.764.html"
    removed_log_file = "D:\Music\MusicBee\Playlists\Logs\playlists_sync 2022-12-27 010938.038.html"

    created_playlists, updated_playlists, removed_playlists = collect_playlists_from_log_file(newest_file)
    print("created playlists: ")
    print(created_playlists)
    print("updated playlists: ")
    print(updated_playlists)
    print("removed playlists: ")
    print(removed_playlists)
    
    print("")
    print("--------- One line convertion test --------------")
    test_line = "../../Library/Eminem/Eyo/Rivers.mp3"
    conversion_test = re.sub(REGEX_PATTERN_REPLACE_WITH_INTERNAL_DRIVE_PATH, DEFAULT_NVIDIA_SHIELD_MUSIC_DIR, test_line)
    print(test_line + "was converted to: " + conversion_test)

    print("")
    print("--------- Playlist conversion test --------------")
    orginal_playlist_path = DEFAULT_UNMODIFIED_PLAYLISTS_DIR + "Genres/Folk.m3u"
    target_playlist_path = DEFAULT_CONVERTED_PLAYLISTS_DIR + "Genres/Folk.m3u"
    convert_playlist_for_plex(orginal_playlist_path, target_playlist_path)
    with open(target_playlist_path, mode="r", encoding="utf-8") as fin:
        print(fin.read())
    
        
if __name__ == '__main__':
    main()