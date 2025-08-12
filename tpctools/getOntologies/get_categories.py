import urllib.request
import json
import time
import re
from datetime import datetime

from agr_curation_api import APIConfig, AGRCurationAPIClient
from dateutil.relativedelta import relativedelta
import argparse
from os import rename

from get_sgd_specific_categories import create_obo_file
from fastapi_okta.okta_utils import get_authentication_token, generate_headers

API_URL = "https://curation.alliancegenome.org/api/"
PAGE_LIMIT = 1000

def get_category_data(mod, download_all=False):

    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)
    
    if download_all:
        download_all_ontologies(mod, id_prefix)

    now = time.asctime()
    token = get_authentication_token()
    headers = generate_headers(token)
    params = {
        "searchFilters": {
            "dataProviderFilter": {
                "dataProvider.abbreviation": {
                    "queryString": mod,
                    "tokenOperator": "OR"
                }
            }
        },
        "sortOrders": [],
        "aggregations": [],
        "nonNullFieldsTable": []
    }

    if mod == 'WB':
        # generate_entity_list_from_a_team(mod, 'gene', params, id_prefix, species_name, filename_id, now, token, headers)
        # generate_entity_list_from_a_team(mod, 'gene_synonym', params, 's' + id_prefix, species_name, filename_id, now, token, headers)
        generate_entity_list_from_a_team_api(mod, 'gene', id_prefix, species_name, filename_id, now,
                                             generate_synonyms=True)
        generate_entity_list_from_a_team(mod, 'protein', params, id_prefix, species_name, filename_id, now, token, headers)
        generate_entity_list_from_a_team(mod, 'protein_synonym', params, 's' + id_prefix, species_name, filename_id, now, token, headers)
        update_entity_list(mod, 'allele', params, id_prefix, species_name, filename_id, now, token, headers)
    elif mod == 'MGI':
        generate_entity_list_from_a_team(mod, 'gene', params, id_prefix, species_name, filename_id, now, token, headers)
    elif mod == 'ZFIN':
        generate_entity_list_from_a_team(mod, 'gene', params, id_prefix, species_name, filename_id, now, token, headers)
        generate_entity_list_from_a_team(mod, 'allele', params, id_prefix, species_name, filename_id, now, token, headers)
        generate_entity_list_from_a_team(mod, 'fish', params, id_prefix, species_name, filename_id, now, token, headers)
    elif mod == 'FB':
        generate_entity_list_from_a_team(mod, 'gene', params, id_prefix, species_name, filename_id, now, token, headers)
    elif mod == 'SGD':
        generate_entity_list_from_a_team(mod, 'gene', params, id_prefix, species_name, filename_id, now, token, headers)
        generate_entity_list_from_a_team(mod, 'allele', params, id_prefix, species_name, filename_id, now, token, headers)
        create_obo_file('tppsc', 'Protein', "protein_saccharomyces_cerevisiae.obo")
        create_obo_file('tpssc', 'Strain', "strain_saccharomyces_cerevisiae.obo")


def update_entity_list(mod, entity_type, params, id_prefix, species_name, filename_id, now, token, headers):
    ## can make it work for other entities as well
    params["sortOrders"] = [
        {
            "field": "dbDateUpdated",
            "order": -1
        }
    ]

    current_page = 0
    
    new_entities = set()
    obsolete_entities = set()
    records_printed = 0
    current_date = datetime.now()
    date_two_months_ago = (current_date - relativedelta(months=2)).date()    
    while True:
        url = f"{API_URL}{entity_type}/search?limit={PAGE_LIMIT}&page={current_page}"
        request_data_encoded = json.dumps(params).encode('utf-8')
        request = urllib.request.Request(url, data=request_data_encoded)
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Content-type", "application/json")
        request.add_header("Accept", "application/json")

        with urllib.request.urlopen(request) as response:
            resp_obj = json.loads(response.read().decode("utf8"))

        if resp_obj['returnedRecords'] < 1:
            break
        done = False
        for result in resp_obj['results']:
            # example result['dbDateUpdated']: '2024-01-19T08:57:10.553475Z'
            dateUpdatedStr = result['dbDateUpdated']
            dateUpdated = datetime.fromisoformat(dateUpdatedStr.rstrip('Z')).date()
            if dateUpdated < date_two_months_ago:
                done = True
                break
            records_printed += 1
            print(dateUpdated, result[entity_type+'Symbol']['formatText'], result['obsolete'], result['internal'])
            if not result['obsolete'] and not result['internal']:
                new_entities.add(result[entity_type+'Symbol']['formatText'])
            else:
                obsolete_entities.add(result[entity_type+'Symbol']['formatText'])

        current_page += 1
        print(f"Total {entity_type.capitalize()} Records Printed {records_printed} of {resp_obj['totalResults']}")
        if done:
            break
    if len(new_entities) == 0:
        return   
    entity_list_file = f"{entity_type}_{filename_id}.obo"
    curr_entity_list_file = f"/data/textpresso/obofiles4production/{entity_list_file}"
    process_entities(curr_entity_list_file, entity_list_file, new_entities, obsolete_entities, entity_type, id_prefix, species_name)
    

def process_entities(curr_file_with_path, new_file_with_path, new_entities, obsolete_entities, entity_type, id_prefix, species_name):

    # read current entities and determine the highest ID
    entity_dict, max_id = read_entities(curr_file_with_path)
    tp_root_id = f"tp{entity_type[0]}{id_prefix}:0000000"
    root_name = entity_type.capitalize()
    # create a new file
    with open(curr_file_with_path, 'r') as old_file, open(new_file_with_path, 'w') as new_file:
        content = old_file.readlines()
        i = 0
        skip_entry = False
        block_buffer = []
        while i < len(content):
            line = content[i]
            if '[Term]' in line:
                # write previous block if not skipping and buffer is not empty
                if not skip_entry and block_buffer:
                    new_file.writelines(block_buffer)
                # reset for new block
                skip_entry = False
                block_buffer = []

            # buffer the line
            block_buffer.append(line)

            if 'name: ' in line:
                entity_name = line.strip().split('name: ')[1]
                if entity_name in obsolete_entities:
                    skip_entry = True  # mark this block to be skipped

            # check if next line starts a new term or if it's the end of the file
            if i + 1 == len(content) or '[Term]' in content[i + 1]:
                if not skip_entry:
                    new_file.writelines(block_buffer)  # write the whole block if not skipping
                block_buffer = []  # reset the block buffer for the next term
                skip_entry = False  # reset skipping flag

            i += 1

        # append new entities if they are not already in the file
        for entity_name in new_entities:
            if entity_name not in entity_dict:
                max_id += 1
                new_id = f"tpace:{max_id:07d}"
                new_file.write(f"\n[Term]\nid: {new_id}\nname: {entity_name}\nis_a: {tp_root_id} ! {root_name} ({species_name})\n")


def read_entities(file_path):
    
    with open(file_path, 'r') as file:
        content = file.read()

    ids = re.findall(r'^id: (\S+)', content, re.MULTILINE)
    names = re.findall(r'^name: (\S+)', content, re.MULTILINE)
    entity_dict = dict(zip(names, ids))
    max_id = max(int(id.split(':')[-1]) for id in ids)
    return entity_dict, max_id


def generate_entity_list_from_a_team_api(mod, entity_type, id_prefix, species_name, filename_id, now,
                                         generate_synonyms=False):
    """
    Generate entity list files using AGRCurationAPIClient.
    Processes both genes and gene synonyms in a single pass to avoid duplicate API calls.
    """
    # Create API configuration and client
    api_config = APIConfig()
    api_client = AGRCurationAPIClient(api_config)

    root_name = entity_type.capitalize()
    synonym_root_name = entity_type.capitalize().replace("_synonym", " Synonym")

    
    # Initialize file writers and counters
    entity_file = None
    synonym_file = None
    records_printed = 0
    synonym_records_printed = 0
    found_synonyms = set()
    
    # Setup gene file
    if generate_synonyms:
        entity_list_file = f"{entity_type}_{filename_id}.obo"
        entity_file = open(entity_list_file, "w")
        root_id = f"tpg{id_prefix}:0000000"
        write_obo_file_header(entity_file, root_id, root_name, species_name, now)
    
    # Setup synonym file
    if generate_synonyms:
        synonym_list_file = f"gene_synonym_{filename_id}.obo"
        synonym_file = open(synonym_list_file, "w")
        synonym_root_id = f"tpgs{id_prefix}:0000000"
        write_obo_file_header(synonym_file, synonym_root_id, synonym_root_name, species_name, now)
    
    try:
        # Fetch genes using AGRCurationAPIClient
        current_page = 0
        
        while True:
            try:
                entities = []
                # Get genes from API client
                if entity_type == 'gene':
                    entities = api_client.get_genes(data_provider=mod, limit=PAGE_LIMIT, page=current_page)
                
                # Check if we got any results
                if not entities or len(entities) == 0:
                    break
                
                # Process each gene
                for entity in entities:
                    # Skip obsolete or internal genes
                    if hasattr(entity, 'obsolete') and entity.obsolete:
                        continue
                    if hasattr(entity, 'internal') and entity.internal:
                        continue
                    
                    # Process entity name
                    entity_name = None
                    entity_symbol = None
                    if entity_type == 'gene':
                        entity_symbol = entity.gene_symbol
                    if hasattr(entity_symbol, 'format_text'):
                        entity_name = entity_symbol.format_text
                    elif hasattr(entity_symbol, 'display_text'):
                        entity_name = entity_symbol.display_text

                    if entity_name:
                        # Apply MOD-specific formatting
                        if mod == 'WB':
                            gene_name = entity_name.lower()

                        records_printed += 1
                        tp_id = f"tpg{id_prefix}:{records_printed:07d}"
                        entity_file.write(f"\n[Term]\nid: {tp_id}\nname: {entity_name}\n")
                        entity_file.write(f"is_a: tpg{id_prefix}:0000000 ! {root_name} ({species_name})\n")

                    # Process synonyms
                    if generate_synonyms:
                        synonyms = []
                        if entity_type == "gene" and hasattr(entity, 'gene_synonyms'):
                            synonyms = entity.gene_synonyms
                        for synonym in synonyms:
                            synonym_name = None
                            if hasattr(synonym, 'display_text'):
                                synonym_name = synonym.display_text
                            elif hasattr(synonym, 'format_text'):
                                synonym_name = synonym.format_text
                            
                            # Skip if already processed or empty
                            if not synonym_name or synonym_name in found_synonyms:
                                continue
                            
                            found_synonyms.add(synonym_name)
                            
                            # Apply MOD-specific formatting
                            if mod == 'WB':
                                synonym_name = synonym_name.lower()
                            
                            synonym_records_printed += 1
                            tp_id = f"tpgs{id_prefix}:{synonym_records_printed:07d}"
                            synonym_file.write(f"\n[Term]\nid: {tp_id}\nname: {synonym_name}\n")
                            synonym_file.write(f"is_a: tpgs{id_prefix}:0000000 ! {synonym_root_name} ({species_name})\n")
                
                # Progress update
                current_page += 1
                print(f"Page {current_page}: Genes: {records_printed}, "
                      f"Synonyms: {synonym_records_printed}")
                
                # If we got less than PAGE_LIMIT results, we've reached the end
                if len(entities) < PAGE_LIMIT:
                    break
                    
            except Exception as e:
                print(f"Error fetching page {current_page}: {e}")
                break
        
        # Print final statistics
        print(f"Total {root_name} Records Written: {records_printed}")
        if generate_synonyms:
            print(f"Total {synonym_root_name} Records Written: {synonym_records_printed}")
            
    finally:
        # Ensure files are properly closed
        if entity_file:
            entity_file.close()
        if synonym_file:
            synonym_file.close()


def generate_entity_list_from_a_team(mod, entity_type, params, id_prefix, species_name, filename_id, now, token, headers):
    if entity_type not in ["gene", "allele", "fish", "protein", "gene_synonym", "protein_synonym"]:
        return

    if entity_type.startswith("protein") and mod != "WB":
        return
    found_synonyms = set()
    entity_list_file = f"{entity_type}_{filename_id}.obo"
    with open(entity_list_file, "w") as f:
        entity_type_short = entity_type.split('_')[0]
        entity_type_short = "agm" if entity_type_short == "fish" else "gene" if entity_type_short == "protein" else entity_type_short
        tp_root_id = f"tp{entity_type[0]}{id_prefix}:0000000"
        root_name = entity_type.capitalize()
        root_name = root_name.replace("_synonym", " Synonym")
        write_obo_file_header(f, tp_root_id, root_name, species_name, now)

        current_page = 0
        records_printed = 0
        while True:
            url = f"{API_URL}{entity_type_short}/search?limit={PAGE_LIMIT}&page={current_page}"
            request_data_encoded = json.dumps(params).encode('utf-8')
            request = urllib.request.Request(url, data=request_data_encoded)
            request.add_header("Authorization", f"Bearer {token}")
            request.add_header("Content-type", "application/json")
            request.add_header("Accept", "application/json")

            with urllib.request.urlopen(request) as response:
                resp_obj = json.loads(response.read().decode("utf8"))

            if resp_obj['returnedRecords'] < 1:
                break

            for result in resp_obj['results']:
                if result['obsolete'] or result['internal']:
                    continue
                entity_name = get_entity_name(entity_type, result, mod)
                if entity_name:
                    if mod != 'WB' or not entity_type.endswith("_synonym"):
                        records_printed += 1
                        tp_id = f"tp{entity_type[0]}{id_prefix}:{records_printed:07d}"
                        f.write(f"\n[Term]\nid: {tp_id}\nname: {entity_name}\nis_a: {tp_root_id} ! {root_name} ({species_name})\n")
                        
                if entity_type_short in ["gene", "allele"]:
                    if mod != 'WB' or entity_type.endswith("_synonym"):
                        synonymField = f"{entity_type_short}Synonyms"
                        if synonymField in result:
                            for s in result[synonymField]:
                                alias_name = s["displayText"]
                                if alias_name in found_synonyms:
                                    continue
                                found_synonyms.add(alias_name)
                                records_printed += 1
                                tp_id = f"tp{entity_type[0]}{id_prefix}:{records_printed:07d}"
                                if mod == "WB":
                                    if entity_type.startswith("protein"):
                                        alias_name = alias_name.upper()
                                    elif entity_type.startswith("gene"):
                                        alias_name = alias_name.lower()
                                f.write(f"\n[Term]\nid: {tp_id}\nname: {alias_name}\nis_a: {tp_root_id} ! {root_name} ({species_name})\n")                            
            current_page += 1
            print(f"Total {entity_type.capitalize()} Records Printed {records_printed} of {resp_obj['totalResults']}")


def get_entity_name(entity_type, result, mod=None):
    if entity_type == 'gene':
        gene_name = result['geneSymbol']['formatText']
        if mod and mod == 'WB':
            return gene_name.lower()
        return gene_name
    elif entity_type == 'protein':
        ## currently just for WB
        gene_name = result['geneSymbol']['formatText']
        return gene_name.upper()
    elif entity_type == 'allele':
        return result['alleleSymbol']['formatText']
    elif entity_type == 'fish':
        if result['subtype']['name'] != 'fish':
            return None
        if 'agmFullName' in result and 'displayText' in result['agmFullName']:
            return result['agmFullName']['displayText']
        return None
 

def write_obo_file_header(f, tp_root_id, root_name, species_name, now):
    f.write("format-version: 1.2\n")
    f.write(f"date: {now}\n")
    f.write("saved-by: Textpresso\n")
    f.write("auto-generated-by: get_categories.py\n\n")
    f.write("[Term]\n")
    f.write(f"id: {tp_root_id}\n")
    f.write(f"name: {root_name} ({species_name})\n")

def download_all_ontologies(mod, id_prefix):

    urllib.request.urlretrieve("https://current.geneontology.org/ontology/go-basic.obo", "go.obo_old")
    urllib.request.urlretrieve("https://purl.obolibrary.org/obo/doid.obo", "doid.obo_old")
    urllib.request.urlretrieve("https://purl.obolibrary.org/obo/chebi.obo", "chebi.obo_old")
    urllib.request.urlretrieve("https://purl.obolibrary.org/obo/so.obo", "so.obo_old")
    remove_obsolete_terms("go.obo_old", "go.obo")
    remove_obsolete_terms("doid.obo_old", "doid.obo")
    remove_obsolete_terms("chebi.obo_old", "chebi.obo")
    remove_obsolete_terms("so.obo_old", "so.obo")
    generate_flattened_ontology_file("go.obo", id_prefix)
    generate_flattened_ontology_file("doid.obo", id_prefix)
    generate_flattened_ontology_file("chebi.obo", id_prefix)
    generate_flattened_ontology_file("so.obo", id_prefix)

    if mod == 'WB':
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/wbbt.obo", "wbbt.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/wbls.obo", "wbls.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/pato.obo", "pato.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/wbphenotype.obo", "wbphenotype.obo_old")
        remove_obsolete_terms("wbbt.obo_old", "wbbt.obo")
        remove_obsolete_terms("wbls.obo_old", "wbls.obo")
        remove_obsolete_terms("pato.obo_old", "pato.obo")
        remove_obsolete_terms("wbphenotype.obo_old", "wbphenotype.obo")
    elif mod == 'ZFIN':
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/zfa.obo", "zfa.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/cl.obo", "cl.obo_old")
        remove_obsolete_terms("zfa.obo_old", "zfa.obo")
        remove_obsolete_terms("cl.obo_old", "cl.obo")
    elif mod == 'MGI':
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/emapa.obo", "emapa.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/ma.obo", "ma.obo_old")
        remove_obsolete_terms("emapa.obo_old", "emapa.obo")
        remove_obsolete_terms("ma.obo_old", "ma.obo")
    elif mod == 'FB':
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/fbbt/fly_anatomy.obo", "fly_anatomy.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/fbdv/fbdv-simple.obo", "fbdv_simple.obo_old")
        urllib.request.urlretrieve("https://purl.obolibrary.org/obo/fbcv/fbcv-simple.obo", "fbcv_simple.obo_old")
        remove_obsolete_terms("fly_anatomy.obo_old", "fly_anatomy.obo")
        remove_obsolete_terms("fbdv_simple.obo_old", "fbdv_simple.obo")
        remove_obsolete_terms("fbcv_simple.obo_old", "fbcv_simple.obo")


def remove_obsolete_terms(input_file_path, output_file_path):
    with open(input_file_path, 'r') as file:
        lines = file.readlines()

    write_block = True
    term_block = []
    new_content = []
    
    # process each line in the OBO file
    for line in lines:
        # check for the start of a new term block
        if line.startswith('[Term]'):
            # start a new block, assume it's not obsolete unless proven otherwise
            write_block = True
            term_block = [line]  # Start collecting lines for this term block
        elif line.strip() == '':
            # end of a block
            if write_block and term_block:
                # if not obsolete, add the term block to new content
                new_content.extend(term_block)
                new_content.append(line)  # add a newline to separate terms
            term_block = []  # reset the term_block for the next term
        else:
            # collect lines for the current term block
            if 'is_obsolete: true' in line:
                # set the flag to not write this block if obsolete
                write_block = False
            term_block.append(line)
    
    # write the filtered content to a new file
    with open(output_file_path, 'w') as file:
        file.writelines(new_content)


def generate_flattened_ontology_file(obo_file, id_prefix):

    ontology_details = {
        'go': ("Gene Ontology (flattened, fast loading)", f"tpgf{id_prefix}:0000000"),
        'so': ("Sequence Ontology (flattened, fast loading)", f"tpsf{id_prefix}:0000000"),
        'doid': ("Disease Ontology (flattened, fast loading)", f"tpdf{id_prefix}:0000000"),
        'chebi': ("ChEBI Ontology (flattened, fast loading)", f"tpcf{id_prefix}:0000000")
    }

    file_prefix = obo_file.split('.')[0]
    root_term, root_id = ontology_details.get(file_prefix, (None, None))
    if root_term is None:
        print(f"No ontology details found for the file prefix: {file_prefix}")
        return

    flattened_file = f"{file_prefix}_flattened.obo"

    termType = None
    with open(obo_file, 'r') as f, open(flattened_file, 'w') as fw:
        for count, line in enumerate(f, start=1):
            if count < 5:
                fw.write(line)
            elif count == 5:
                fw.write(f"\n[Term]\nid: {root_id}\nname: {root_term}\n\n")
            if line.strip().startswith("[") and line.strip().endswith("]"):
                termType = line.strip()
            for text in ["[Term]", "id: ", "name: ", "def: ", "synonym: ", "xref: "]:
                if line.startswith(text):
                    fw.write(line)
            if count > 5 and line.strip() == '' and termType == "[Term]":
                fw.write(f"is_a: {root_id} ! {root_term}\n\n")
            if line.startswith("[Typedef]"):
                break

    print(f"Flattened file created: {flattened_file}")

    
def get_id_prefix_species_name(mod):
    mod_info = {
        'SGD': ("sc", "S. cerevisiae", "saccharomyces_cerevisiae"),
        'WB': ("ce", "C. elegans", "caenorhabditis_elegans"),
        'MGI': ("mm", "M. musculus", "mus_musculus"),
        'ZFIN': ("dr", "D. rerio", "danio_rerio"),
        'FB': ("dm", "D. melanogaster", "drosophila_melanogaster"),
        'RGD': ("rn", "R. norvegicus", "rattus_norvegicus"),
        'XB': ("xl", "X. laevis", "xenopus_laevis")
    }
    return mod_info.get(mod, ("", "", ""))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mod', action='store', type=str, help='MOD to dump',
                        choices=['SGD', 'WB', 'FB', 'ZFIN', 'MGI', 'RGD', 'XB'], required=True)
    parser.add_argument('-a', '--all', action='store_true', help="download all ontologies")
    args = parser.parse_args()
    get_category_data(args.mod, args.all)
    
