"""Conservative source-work grouping for quota accounting, independent of captions."""
import re
import unicodedata

VERSION = 'movie_title_year_v2'

def identify(source):
    dataset = source.get('dataset', source.get('source'))
    metadata = source.get('download_provenance', {}).get('observed_metadata', source.get('observed_metadata', {}))
    title = metadata.get('title', '')
    name = year = None
    method = 'video_id_fallback'
    if dataset == 'muss':
        # Movieclips legacy titles put the numbered excerpt BEFORE the release year.
        # e.g. Film (3/10) Movie CLIP - Scene Name (2002) HD.
        numbered = re.match(r'^(.*?)\s*\(\d+/\d+\)\s*Movie\s+CLIP\b', title, re.I)
        years = re.findall(r'\(((?:19|20)\d{2})\)', title)
        if numbered and years:
            name, year, method = numbered.group(1), years[-1], 'numbered_movieclips_title'
        else:
            leading = re.match(r'^(.*?)\s*\(((?:19|20)\d{2})\)', title)
            if leading:
                name, year, method = leading.group(1), leading.group(2), 'title_before_release_year'
                # Movieclips also uses "Scene Name Scene - Film (2023)".
                scene_prefix = re.search(r'\bScene\s*[-–—]\s*(.+)$', name, re.I)
                if scene_prefix:
                    name, method = scene_prefix.group(1), 'scene_prefix_then_film'
    if name:
        normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
        normalized = re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')
        key = f'film:{normalized}:{year}'
    else:
        key = f"{dataset}:{source['video_id']}"
    return {'key': key, 'version': VERSION, 'method': method, 'observed_title': title,
            'cross_url_reuploads_exhaustively_resolved': False}

def work_key(source):
    return identify(source)['key']
