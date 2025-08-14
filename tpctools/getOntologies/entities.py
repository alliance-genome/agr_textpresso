"""
Entity processing module for AGR Textpresso.

This module contains functions for processing biological entities (genes, alleles, fish)
from the Alliance of Genome Resources API and generating OBO files.
"""

import time
import re
from datetime import datetime
from typing import Set, Optional, Any

from agr_curation_api import APIConfig, AGRCurationAPIClient  # type: ignore
from dateutil.relativedelta import relativedelta

PAGE_LIMIT = 1000


def get_id_prefix_species_name(mod: str) -> tuple[str, str, str]:
    """Get ID prefix, species name, and filename ID for a given MOD."""
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


def process_entities(curr_file_with_path: str, new_file_with_path: str, new_entities: Set[str],
                     obsolete_entities: Set[str], entity_type: str, id_prefix: str,
                     species_name: str) -> None:
    """Process entities by updating an existing OBO file with new and obsolete entities."""
    # read current entities and determine the highest ID
    entity_dict, max_id = read_entities(curr_file_with_path)
    tp_root_id = f"tp{entity_type[0]}{id_prefix}:0000000"
    root_name = entity_type.capitalize()
    # create a new file
    with open(curr_file_with_path, 'r') as old_file, open(new_file_with_path, 'w') as new_file:
        content = old_file.readlines()
        i = 0
        skip_entry = False
        block_buffer: list[str] = []
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
                new_file.write(f"\n[Term]\nid: {new_id}\nname: {entity_name}\n"
                               f"is_a: {tp_root_id} ! {root_name} ({species_name})\n")


def read_entities(file_path: str) -> tuple[dict[str, str], int]:
    """Read entities from an OBO file and return entity dictionary and max ID."""
    with open(file_path, 'r') as file:
        content = file.read()

    ids = re.findall(r'^id: (\S+)', content, re.MULTILINE)
    names = re.findall(r'^name: (\S+)', content, re.MULTILINE)
    entity_dict = dict(zip(names, ids))
    max_id = max(int(entity_id.split(':')[-1]) for entity_id in ids)
    return entity_dict, max_id


def get_name_from_entity(entity_symbol: Any) -> Optional[str]:
    """Extract name from an entity symbol object."""
    if entity_symbol is None:
        return None
    if hasattr(entity_symbol, 'formatText'):
        return entity_symbol.formatText
    elif hasattr(entity_symbol, 'displayText'):
        return entity_symbol.displayText
    return None


def generate_entity_list_from_a_team_api(mod: str, entity_type: str, generate_synonyms: bool = False,
                                         all_uppercase_file_name: Optional[str] = None) -> None:
    """
    Generate entity list files using AGRCurationAPIClient.

    Args:
        mod: Model organism database (e.g., 'WB', 'MGI')
        entity_type: Type of entity to process ('gene', 'protein')
        generate_synonyms: Whether to also generate synonym files
        all_uppercase_file_name: If provided, read entities from this file and generate uppercase versions
                               (used for WB proteins which are uppercase versions of genes)
    """
    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)
    now = time.asctime()
    
    # Handle uppercase file generation (e.g., WB proteins from genes)
    if all_uppercase_file_name:
        _generate_uppercase_from_source_file(all_uppercase_file_name, entity_type, id_prefix,
                                             species_name, filename_id, now, generate_synonyms)
        return
    
    api_client = _create_api_client()

    # Process entities and optionally synonyms
    entity_writer = _EntityFileWriter(entity_type, id_prefix, species_name, filename_id, now)
    synonym_writer = (_EntityFileWriter(f"{entity_type}_synonym", id_prefix, species_name, filename_id, now)
                      if generate_synonyms else None)

    try:
        _process_entities_from_api(api_client, mod, entity_type, entity_writer, synonym_writer)
    finally:
        entity_writer.close()
        if synonym_writer:
            synonym_writer.close()


def update_entity_list_from_ateam_api(mod: str, entity_type: str) -> None:
    """
    Update existing entity list files with recent changes using AGRCurationAPIClient.
    Only processes entities updated in the last 2 months.

    Args:
        mod: Model organism database (e.g., 'WB', 'MGI')
        entity_type: Type of entity to process ('gene', 'allele', 'fish')
    """
    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)
    api_client = _create_api_client()

    # Collect recently updated entities
    new_entities: Set[str] = set()
    obsolete_entities: Set[str] = set()

    try:
        _collect_updated_entities(api_client, mod, entity_type, new_entities, obsolete_entities)
    except Exception as e:
        print(f"Error collecting updated entities: {e}")
        return

    if len(new_entities) == 0 and len(obsolete_entities) == 0:
        print(f"No updated {entity_type} entities found for {mod}")
        return

    # Update the existing OBO file
    entity_list_file = f"{entity_type}_{filename_id}.obo"
    curr_entity_list_file = f"/data/textpresso/obofiles4production/{entity_list_file}"

    try:
        process_entities(curr_entity_list_file, entity_list_file, new_entities, obsolete_entities,
                         entity_type, id_prefix, species_name)
        print(f"Updated {entity_list_file}: {len(new_entities)} new, {len(obsolete_entities)} obsolete")
    except Exception as e:
        print(f"Error updating entity file: {e}")


def _create_api_client() -> AGRCurationAPIClient:
    """Create and return AGR API client."""
    api_config = APIConfig()  # type: ignore
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
                               entity_writer: '_EntityFileWriter',
                               synonym_writer: Optional['_EntityFileWriter']) -> None:
    """Process entities from API with pagination."""
    current_page = 0
    found_synonyms: Set[str] = set()

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


def _fetch_entities_page(api_client: AGRCurationAPIClient, mod: str, entity_type: str, page: int, updated_after=None):
    """Fetch a single page of entities from the API."""
    if entity_type in ['gene', 'protein']:
        return api_client.get_genes(data_provider=mod, limit=PAGE_LIMIT, page=page, updated_after=updated_after)
    elif entity_type == 'allele':
        return api_client.get_alleles(data_provider=mod, limit=PAGE_LIMIT, page=page, updated_after=updated_after)
    elif entity_type == 'fish':
        return api_client.get_agms(data_provider=mod, limit=PAGE_LIMIT, page=page, updated_after=updated_after)
    return []


def _collect_updated_entities(api_client: AGRCurationAPIClient, mod: str, entity_type: str,
                              new_entities: Set[str], obsolete_entities: Set[str]) -> None:
    """
    Collect recently updated entities (within last 2 months) from the API.

    Note: This function currently fetches all entities as the AGRCurationAPIClient
    doesn't support sorting by dbDateUpdated yet. This should be enhanced when
    the client library supports date-based filtering or sorting.
    """
    current_page = 0
    records_processed = 0
    current_date = datetime.now()
    date_two_months_ago = (current_date - relativedelta(months=2)).isoformat()

    print(f"Collecting {entity_type} entities updated since {date_two_months_ago}")

    while True:
        try:
            entities = _fetch_entities_page(api_client, mod, entity_type, current_page, date_two_months_ago)
            if not entities:
                break

            for entity in entities:
                # Check if entity has a date updated field
                date_updated_str = None
                if hasattr(entity, 'date_updated') and entity.date_updated:
                    date_updated_str = entity.date_updated
                elif hasattr(entity, 'db_date_updated') and entity.db_date_updated:
                    date_updated_str = entity.db_date_updated

                # If we can't get the date, process all entities (fallback behavior)
                if date_updated_str and date_updated_str < date_two_months_ago:
                    continue

                records_processed += 1

                # Check if entity should be skipped (obsolete or internal)
                if _should_skip_entity(entity):
                    entity_name = _get_entity_name_from_api_entity(entity, entity_type, mod)
                    if entity_name:
                        obsolete_entities.add(entity_name)
                    continue

                # Get entity name
                entity_name = _get_entity_name_from_api_entity(entity, entity_type, mod)
                if entity_name:
                    new_entities.add(entity_name)

            current_page += 1
            print(f"Page {current_page}: Processed {records_processed} entities, "
                  f"New: {len(new_entities)}, Obsolete: {len(obsolete_entities)}")

            if len(entities) < PAGE_LIMIT:
                break

        except Exception as e:
            print(f"Error fetching page {current_page}: {e}")
            break


def _get_entity_name_from_api_entity(entity: Any, entity_type: str, mod: str) -> Optional[str]:
    """Extract entity name from API entity object."""
    entity_name = None

    if entity_type == 'gene':
        entity_symbol = getattr(entity, 'gene_symbol', None)
        entity_name = get_name_from_entity(entity_symbol)
        if entity_name and mod == 'WB':
            entity_name = entity_name.lower()
    elif entity_type == 'allele':
        allele_symbol = getattr(entity, 'allele_symbol', None)
        entity_name = get_name_from_entity(allele_symbol)
    elif entity_type == 'fish':
        # For AGM (fish) entities
        if hasattr(entity, 'subtype') and entity.subtype:
            if getattr(entity.subtype, 'name', None) == 'fish':
                agm_full_name = getattr(entity, 'agm_full_name', None)
                entity_name = get_name_from_entity(agm_full_name)

    return entity_name


def _should_skip_entity(entity: Any) -> bool:
    """Check if entity should be skipped (obsolete or internal)."""
    return ((hasattr(entity, 'obsolete') and entity.obsolete) or
            (hasattr(entity, 'internal') and entity.internal))


def _process_single_entity(entity: Any, entity_type: str, mod: str,
                           entity_writer: '_EntityFileWriter',
                           synonym_writer: Optional['_EntityFileWriter'],
                           found_synonyms: Set[str]) -> None:
    """Process a single entity and its synonyms."""
    # Process main entity based on entity type
    entity_symbol = None

    # Extract entity symbol based on entity type
    if entity_type in ['gene', 'protein']:
        if hasattr(entity, 'geneSymbol'):
            entity_symbol = entity.geneSymbol
    elif entity_type == 'allele':
        if hasattr(entity, 'alleleSymbol'):
            entity_symbol = entity.alleleSymbol
    elif entity_type == 'fish':
        # For AGM (fish) entities, check if it's actually a fish subtype
        if hasattr(entity, 'subtype') and entity.subtype:
            if getattr(entity.subtype, 'name', None) == 'fish':
                if hasattr(entity, 'agmFullName'):
                    entity_symbol = entity.agmFullName

    entity_name = get_name_from_entity(entity_symbol)

    if entity_name:
        formatted_name = _apply_mod_formatting(entity_name, mod, entity_type)
        entity_writer.write_entity(formatted_name)

    # Process synonyms if requested
    if synonym_writer:
        synonyms = None

        # Get synonyms based on entity type
        if entity_type in ['gene', 'protein']:
            if hasattr(entity, 'geneSynonyms'):
                synonyms = entity.geneSynonyms
            elif hasattr(entity, 'gene_synonyms'):
                synonyms = entity.gene_synonyms
        elif entity_type == 'allele':
            if hasattr(entity, 'alleleSynonyms'):
                synonyms = entity.alleleSynonyms
            elif hasattr(entity, 'allele_synonyms'):
                synonyms = entity.allele_synonyms
        # Note: fish/agm entities typically don't have synonyms in the old implementation

        if synonyms:
            for synonym in synonyms:
                synonym_name = get_name_from_entity(synonym)
                if synonym_name and synonym_name not in found_synonyms:
                    found_synonyms.add(synonym_name)
                    formatted_synonym = _apply_mod_formatting(synonym_name, mod, entity_type)
                    synonym_writer.write_entity(formatted_synonym)


class _EntityFileWriter:
    """Helper class to manage OBO file writing for entities."""

    def __init__(self, entity_type: str, id_prefix: str, species_name: str,
                 filename_id: str, now: str) -> None:
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


def _generate_uppercase_from_source_file(source_file_name: str, target_entity_type: str,
                                         id_prefix: str, species_name: str, filename_id: str,
                                         now: str, generate_synonyms: bool) -> None:
    """
    Generate uppercase entity files by reading from a source file and using file writers.
    Used for WB proteins which are uppercase versions of gene names.
    """
    import os
    
    print(f"Generating {target_entity_type}_{filename_id}.obo from {source_file_name} (uppercase conversion)")
    
    # Check if source file exists (try current directory first, then production directory)
    source_file_path = source_file_name
    if not os.path.exists(source_file_path):
        source_file_path = f"/data/textpresso/obofiles4production/{source_file_name}"
        if not os.path.exists(source_file_path):
            print(f"Source file {source_file_name} not found in current directory or production directory")
            return
    
    # Check if source synonym file exists
    # The pattern is: gene_caenorhabditis_elegans.obo -> gene_synonym_caenorhabditis_elegans.obo
    base_name = source_file_name.replace('.obo', '')
    parts = base_name.split('_', 1)  # Split into 'gene' and 'caenorhabditis_elegans'
    if len(parts) == 2:
        source_synonym_name = f"{parts[0]}_synonym_{parts[1]}.obo"
    else:
        source_synonym_name = source_file_name.replace('.obo', '_synonym.obo')
    
    source_synonym_path = source_synonym_name
    if not os.path.exists(source_synonym_path):
        source_synonym_path = f"/data/textpresso/obofiles4production/{source_synonym_name}"
    has_synonyms = generate_synonyms and os.path.exists(source_synonym_path)
    
    # Create file writers
    entity_writer = _EntityFileWriter(target_entity_type, id_prefix, species_name, filename_id, now)
    synonym_writer = (_EntityFileWriter(f"{target_entity_type}_synonym", id_prefix, species_name, filename_id, now)
                      if has_synonyms else None)
    
    try:
        # Read and process main entity file
        _read_and_convert_to_uppercase(source_file_path, entity_writer, species_name)
        
        # Read and process synonym file if it exists
        if synonym_writer and has_synonyms:
            print(f"Generating {target_entity_type}_synonym_{filename_id}.obo from {source_synonym_name} (uppercase conversion)")
            _read_and_convert_to_uppercase(source_synonym_path, synonym_writer, species_name)
            
    finally:
        entity_writer.close()
        if synonym_writer:
            synonym_writer.close()


def _read_and_convert_to_uppercase(source_file_path: str, writer: '_EntityFileWriter', species_name: str) -> None:
    """Read entity names from source file and write uppercase versions to target writer."""
    with open(source_file_path, 'r') as source_file:
        for line in source_file:
            line = line.strip()
            if line.startswith('name: ') and not line.endswith(f'({species_name})'):
                # This is an entity name line (not the root term)
                name_part = line[6:]  # Remove 'name: '
                writer.write_entity(name_part.upper())


def write_obo_file_header(f: Any, tp_root_id: str, root_name: str,
                          species_name: str, now: str) -> None:
    """Write the header section of an OBO file."""
    f.write("format-version: 1.2\n")
    f.write(f"date: {now}\n")
    f.write("saved-by: Textpresso\n")
    f.write("auto-generated-by: get_categories.py\n\n")
    f.write("[Term]\n")
    f.write(f"id: {tp_root_id}\n")
    f.write(f"name: {root_name} ({species_name})\n")