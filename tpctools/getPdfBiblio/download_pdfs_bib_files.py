import argparse
import logging
import requests
import json
import gzip
from datetime import datetime, timedelta
from os import environ, path, remove, makedirs

from fastapi_okta.okta_utils import get_authentication_token, generate_headers

logging.basicConfig(format='%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

limit = 100
loop_count = 1300
start_count = 0
start_ref_list_url = environ['API_URL'] + "reference/get_textpresso_reference_list/"
start_bib_url = environ['API_URL'] + "reference/get_bib_info/"
start_pdf_url = environ['API_URL'] + "reference/referencefile/download_file/"
default_data_path = environ['DATA_PATH']


def download_files(mod, raw_file_path=None, days_ago=None, start_reference_id=None):

    token = get_authentication_token()
    headers = generate_headers(token)

    logger.info(headers)

    organism = get_organism_name_by_mod(mod)
    if raw_file_path is None:
        raw_file_path = default_data_path
    pdf_dir = path.join(raw_file_path, "pdf/" + organism + "/")
    biblio_dir = path.join(raw_file_path, "bib/" + organism + "/")

    logger.info(pdf_dir)
    logger.info(biblio_dir)

    if start_reference_id is None:
        start_reference_id = 0
    count = start_count
    from_reference_id = start_reference_id
    last_date_updated = None
    if days_ago:
        last_date_updated = get_last_date_updated(days_ago)
    logger.info(f"last_date_updated={last_date_updated}")
    for index in range(loop_count):
        offset = index * limit
        ref_list_url = f"{start_ref_list_url}{mod}?page_size={limit}&from_reference_id={from_reference_id}"
        if last_date_updated:
            ref_list_url = f"{ref_list_url}&files_updated_from_date={last_date_updated}"
        data = get_data_from_url(ref_list_url, headers)
        if data is None:
            continue
        if len(data) == 0:
            break

        """
        email_subject = "Textpresso incremental build report"
        email_message = f"Adding {len(data)} new PDFs" 
        email_utils.send_report(email_subject, email_message)
        """
        
        logger.info(f"offset={offset} data={len(data)}")

        for x in data:

            count += 1
            ref_curie = x['reference_curie']
            reference_id = x['reference_id']

            (md5sum, referencefile_id) = get_md5sum_and_id_of_best_reffile_to_download(mod, x['main_referencefiles'])

            logger.info(f"{count}: {reference_id} {ref_curie} {md5sum} {referencefile_id}")

            ## generating bib files
            bib_url = f"{start_bib_url}{ref_curie}?mod_abbreviation={mod}&return_format=txt" 
            biblioTxt = get_data_from_url(bib_url, headers)
            if not isinstance(biblioTxt, str):
                for index in range(5):
                    biblioTxt = get_data_from_url(bib_url, headers)
                    if isinstance(biblioTxt, str):
                        break
            if isinstance(biblioTxt, str):
                bib_filename = set_file_name(biblio_dir, ref_curie, "bib")
                with open(bib_filename, "w") as bib_file:
                    bib_file.write(biblioTxt)
            else:
                logger.info(f"Error Generating bib file for {ref_curie}. returning {str(biblioTxt)}") 
                exit(1)
            ## downloading PDFs
            pdf_url = f"{start_pdf_url}{referencefile_id}"
            pdf_content = get_data_from_url(pdf_url, headers, 'pdf')
            if 'Internal Server Error' in str(pdf_content):
                for index in range(5):
                    pdf_content = get_data_from_url(pdf_url, headers, 'pdf')
                    if 'Internal Server Error' not in str(pdf_content):
                        break
            if 'Internal Server Error' in str(pdf_content):
                logger.info(f"Error downloading pdf for {ref_curie}. url={pdf_url}")
                exit(1)
            else:
                pdf_filename = set_file_name(pdf_dir, ref_curie, "pdf")
                with open(pdf_filename, "wb") as pdf_file:
                    pdf_file.write(pdf_content)
            
            from_reference_id = reference_id
    
    logger.info("DONE!")


def get_last_date_updated(days_ago):
    current_date = datetime.now()
    past_date = current_date - timedelta(days=int(days_ago))
    last_date_updated = past_date.strftime("%Y-%m-%d")
    return last_date_updated


def set_file_name(data_root_dir, ref_curie, suffix):
    file_path = path.join(data_root_dir, ref_curie)
    if not path.exists(file_path):
        makedirs(file_path)
    return path.join(file_path, ref_curie + "." + suffix)


def get_md5sum_and_id_of_best_reffile_to_download(mod, pdffiles):

    md5sum = None
    referencefile_id = None
    prev_date_created = None
    for x in sorted(pdffiles, key=lambda p: p['date_created']):
        if x['source_is_pmc']:
            md5sum = x['md5sum']
            referencefile_id = x['referencefile_id']
            break
        elif not md5sum or x['date_created'] > prev_date_created:
            md5sum = x['md5sum']
            referencefile_id = x['referencefile_id']
            prev_date_created = x['date_created']
    return(md5sum, referencefile_id)

                    
def get_data_from_url(url, headers, file_type='json'):

    try:
        response = requests.request("GET", url, headers=headers)
        # response.raise_for_status()  # Check if the request was successful
        if file_type == 'pdf':
            return response.content
        else:
            content = response.json()
            if content is None:
                content = response.text()
            return content
    except requests.exceptions.RequestException as e:
        logger.info(f"Error occurred for accessing/retrieving data from {url}: error={e}")
        return None

def get_organism_name_by_mod(mod):

    if mod == 'SGD':
        return 'S. cerevisiae'
    if mod == 'WB':
        return 'C. elegans'
    if mod == 'MGI':
        return 'M. musculus'
    if mod == 'ZFIN':
        return 'D. rerio'
    if mod == 'FB':
        return 'D. melanogaster'


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('-m', '--mod', action='store', type=str,
                        help='download pdfs and bib files for MOD',
                        choices=['WB', 'SGD', 'FB', 'ZFIN', 'MGI', 'RGD', 'XB'])

    parser.add_argument('-p', '--raw_file_path', action='store',
                        help='directory_with_full_path for storing the pdfs/bib files')

    parser.add_argument('-f', '--from_reference_id', action='store',
			help='from reference_id for downloading pdfs and generating the biblio files')

    parser.add_argument('-d', '--days_ago', action='store',
                        help='Number of days in the past to filter PDF files, Downloading PDF files added in the past {args.days} days into ABC...')
    
    args = vars(parser.parse_args())

    if not args['mod']:	
        print("Example usage: python3 download_pdfs_bib_files.py -m SGD")
        print("Example usage: python3 download_pdfs_bib_files.py -m SGD -p /data/textpresso/raw_files/ -d 7 -f 0")
        exit()

    download_files(args['mod'], args['raw_file_path'], args['days_ago'], args['from_reference_id'])

