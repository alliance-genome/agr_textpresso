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
        generate_entity_list_from_a_team_api(mod, 'gene', generate_synonyms=True)
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


def get_name_from_entity(entity_symbol):
    # Handle both object attributes and dictionary access
    if entity_symbol is None:
        return None
    
    # If it's a dictionary, extract the text
    if isinstance(entity_symbol, dict):
        if 'formatText' in entity_symbol:
            return entity_symbol['formatText']
        elif 'displayText' in entity_symbol:
            return entity_symbol['displayText']
    
    # If it's an object, use attributes
    if hasattr(entity_symbol, 'format_text'):
        return entity_symbol.format_text
    elif hasattr(entity_symbol, 'display_text'):
        return entity_symbol.display_text
    
    return None


def generate_entity_list_from_a_team_api(mod: str, entity_type: str, generate_synonyms: bool = False) -> None:
    """
    Generate entity list files using AGRCurationAPIClient.
    
    Args:
        mod: Model organism database (e.g., 'WB', 'MGI')
        entity_type: Type of entity to process ('gene', 'protein') 
        generate_synonyms: Whether to also generate synonym files
    """
    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)
    now = time.asctime()
    
    api_client = _create_api_client()
    
    # Process entities and optionally synonyms
    entity_writer = _EntityFileWriter(entity_type, id_prefix, species_name, filename_id, now)
    synonym_writer = _EntityFileWriter('gene_synonym', id_prefix, species_name, filename_id, now) if generate_synonyms else None
    
    try:
        _process_entities_from_api(api_client, mod, entity_type, entity_writer, synonym_writer)
    finally:
        entity_writer.close()
        if synonym_writer:
            synonym_writer.close()


def _create_api_client() -> AGRCurationAPIClient:
    """Create and return AGR API client."""
    api_config = APIConfig()
    return AGRCurationAPIClient(api_config)


def _apply_mod_formatting(name: str, mod: str, entity_type: str) -> str:
    """Apply MOD-specific name formatting."""
    if mod == 'WB':
        if entity_type == 'gene':
            return name.lower()
        elif entity_type == 'protein':
            return name.upper()
    return name


def _process_entities_from_api(api_client: AGRCurationAPIClient, mod: str, entity_type: str, 
                               entity_writer, synonym_writer) -> None:
    """Process entities from API with pagination."""
    current_page = 0
    found_synonyms = set()
    
    while True:
        try:
            entities = _fetch_entities_page(api_client, mod, entity_type, current_page)
            if not entities:
                print(f"No entities returned for {entity_type} page {current_page}")
                break
                
            for entity in entities:
                if _should_skip_entity(entity):
                    continue
                    
                _process_single_entity(entity, entity_type, mod, entity_writer, synonym_writer, found_synonyms)
            
            current_page += 1
            print(f"Page {current_page}: Entities: {entity_writer.records_count}, "
                  f"Synonyms: {synonym_writer.records_count if synonym_writer else 0}")
            
            if len(entities) < PAGE_LIMIT:
                break
                
        except Exception as e:
            print(f"Error fetching page {current_page}: {e}")
            import traceback
            traceback.print_exc()
            break


def _fetch_entities_page(api_client: AGRCurationAPIClient, mod: str, entity_type: str, page: int):
    """Fetch a single page of entities from the API."""
    if entity_type in ['gene', 'protein']:
        return api_client.get_genes(data_provider=mod, limit=PAGE_LIMIT, page=page)
    return []


def _should_skip_entity(entity) -> bool:
    """Check if entity should be skipped (obsolete or internal)."""
    return ((hasattr(entity, 'obsolete') and entity.obsolete) or 
            (hasattr(entity, 'internal') and entity.internal))


def _process_single_entity(entity, entity_type: str, mod: str, entity_writer, synonym_writer, found_synonyms: set) -> None:
    """Process a single entity and its synonyms."""
    # Process main entity based on entity type
    entity_symbol = None
    
    # Try different ways to access gene_symbol based on how API returns data
    if entity_type in ['gene', 'protein']:
        if hasattr(entity, 'gene_symbol'):
            entity_symbol = entity.gene_symbol
        elif hasattr(entity, '__dict__') and 'gene_symbol' in entity.__dict__:
            entity_symbol = entity.__dict__['gene_symbol']
    
    entity_name = get_name_from_entity(entity_symbol)
    
    if entity_name:
        formatted_name = _apply_mod_formatting(entity_name, mod, entity_type)
        entity_writer.write_entity(formatted_name)
    
    # Process synonyms if requested
    if synonym_writer:
        synonyms = None
        if hasattr(entity, 'gene_synonyms'):
            synonyms = entity.gene_synonyms
        elif hasattr(entity, '__dict__') and 'gene_synonyms' in entity.__dict__:
            synonyms = entity.__dict__['gene_synonyms']
            
        if synonyms:
            for synonym in synonyms:
                synonym_name = get_name_from_entity(synonym)
                if synonym_name and synonym_name not in found_synonyms:
                    found_synonyms.add(synonym_name)
                    formatted_synonym = _apply_mod_formatting(synonym_name, mod, entity_type)
                    synonym_writer.write_entity(formatted_synonym)


class _EntityFileWriter:
    """Helper class to manage OBO file writing for entities."""
    
    def __init__(self, entity_type: str, id_prefix: str, species_name: str, filename_id: str, now: str):
        self.entity_type = entity_type
        self.id_prefix = id_prefix
        self.species_name = species_name
        self.records_count = 0
        
        # Determine file naming and ID prefixes
        if entity_type == 'gene_synonym':
            self.filename = f"gene_synonym_{filename_id}.obo"
            self.tp_prefix = f"tpgs{id_prefix}"
            self.root_name = "Gene Synonym"
        else:
            self.filename = f"{entity_type}_{filename_id}.obo"
            self.tp_prefix = f"tpg{id_prefix}"
            self.root_name = entity_type.capitalize()
        
        self.root_id = f"{self.tp_prefix}:0000000"
        self.file_handle = open(self.filename, "w")
        write_obo_file_header(self.file_handle, self.root_id, self.root_name, species_name, now)
    
    def write_entity(self, name: str) -> None:
        """Write an entity to the OBO file."""
        self.records_count += 1
        tp_id = f"{self.tp_prefix}:{self.records_count:07d}"
        self.file_handle.write(f"\n[Term]\nid: {tp_id}\nname: {name}\n")
        self.file_handle.write(f"is_a: {self.root_id} ! {self.root_name} ({self.species_name})\n")
    
    def close(self) -> None:
        """Close the file handle and print statistics."""
        if self.file_handle:
            self.file_handle.close()
            print(f"Total {self.root_name} Records Written: {self.records_count}")


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
    
