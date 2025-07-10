import urllib.request
import json
import time
import argparse
from getPdfBiblio.okta_utils import (
    generate_headers
)



##GENERIC ONTOLOGIES
##downloadLocation = '.'
#urllib.request.urlretrieve("http://current.geneontology.org/ontology/go-basic.obo",downloadLocation)
#urllib.request.urlretrieve("http://purl.obolibrary.org/obo/doid.obo",downloadLocation)
#urllib.request.urlretrieve("http://purl.obolibrary.org/obo/chebi.obo",downloadLocation)
#urllib.request.urlretrieve("http://purl.obolibrary.org/obo/so.obo",downloadLocation)
#urllib.request.urlretrieve("http://purl.obolibrary.org/obo/wbbt.obo",downloadLocation)

parser = argparse.ArgumentParser()
parser.add_argument('--token', dest='token', type=str, help='A team token from curation site')
parser.add_argument('--mod', dest='mod', type=str, help='Mod to procoess')
args = parser.parse_args()

token = args.token
headers = generate_headers(token)

mod = args.mod
page_limit = 1000
current_page = 0
records_printed = 0
ateam_site = "beta-curation.alliancegenome.org"
time = time.asctime()

if mod == 'sgd':
    id_prefix = 'sc'
    species_name = "S. cerevisiae"
elif mod == 'wb':
    id_prefix = 'ce'
    species_name = "C. elegans"

params = {"searchFilters":{"dataProviderFilter":{"dataProvider.abbreviation":{"queryString":mod,"tokenOperator":"OR"}}},"sortOrders":[],"aggregations":[],"nonNullFieldsTable":[]}

##Gene List Generation
f = open(f"gene_list_{mod}.obo", "w")
f.write("format-version: 1.2\n")
f.write(f"date: {time}\n")
f.write("saved-by: Textpresso\n")
f.write("auto-generated-by: get_categories.py\n\n")

f.write("[Term]\n")
f.write(f"id: tpg{id_prefix}:0000000\n")
f.write(f"name: Gene ({species_name})\n")

while True:
    url = f'https://alpha-curation.alliancegenome.org/api/gene/search?limit={page_limit}&page={current_page}'
    request_body = params
    request_data_encoded = json.dumps(request_body)
    request_data_encoded_str = str(request_data_encoded)
    request = urllib.request.Request(url=url, data=request_data_encoded_str.encode('utf-8'))
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-type", "application/json")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request) as response:
        resp = response.read().decode("utf8")
        resp_obj = json.loads(resp)
    if resp_obj['returnedRecords'] < 1:
        break
    for result in resp_obj['results']:
        records_printed += 1
        f.write(f"\n[Term]\nid: tpg{id_prefix}:{records_printed:07d}\nname: {result['geneSymbol']['formatText']}\nis_a: tpg{id_prefix}:0000000 ! Gene ({species_name})\n")
    current_page += 1
    print (f"Total Gene Records Printed {records_printed} of {resp_obj['totalResults']}")
f.close()

##Allele List Generation
f = open(f"allele_list_{mod}.obo", "w")
f.write("format-version: 1.2\n")
f.write(f"date: {time}\n")
f.write("saved-by: Textpresso\n")
f.write("auto-generated-by: get_categories.py\n\n")

f.write("[Term]\n")
f.write(f"id: tpa{id_prefix}:0000000\n")
f.write(f"name: Allele ({species_name})\n")
current_page = 0
records_printed = 0

while True:
    url = f'https://alpha-curation.alliancegenome.org/api/allele/search?limit={page_limit}&page={current_page}'
    request_body = params
    request_data_encoded = json.dumps(request_body)
    request_data_encoded_str = str(request_data_encoded)
    request = urllib.request.Request(url=url, data=request_data_encoded_str.encode('utf-8'))
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-type", "application/json")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request) as response:
        resp = response.read().decode("utf8")
        resp_obj = json.loads(resp)
    if resp_obj['returnedRecords'] < 1:
        break
    for result in resp_obj['results']:
        if 'alleleSymbol' in result:
            records_printed += 1
            f.write(f"\n[Term]\nid: tpa{id_prefix}:{records_printed:07d}\nname: {result['alleleSymbol']['formatText']}\nis_a: tpa{id_prefix}:0000000 ! Allele ({species_name})\n")
        else:
            print('Skipping entry...')
            print(result)
    current_page += 1
    print(f"Total Allele Records Printed {records_printed} of {resp_obj['totalResults']}")
f.close()
