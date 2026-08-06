from .. import wiki_service


def get_compiled_hashes():
    return wiki_service.load_source_hashes()


def save_file_hashes(existing_hashes, processed_files):
    for f in processed_files:
        existing_hashes[f['title']] = f['hash']
    wiki_service.save_source_hashes(existing_hashes)


def detect_changed_files(article_files, compiled_hashes):
    changed = []
    for f in article_files:
        if f['title'] not in compiled_hashes or compiled_hashes[f['title']] != f['hash']:
            changed.append(f)
    return changed
