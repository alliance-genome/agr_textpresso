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

MOD_TAXON_MAPPING = {
    'RGD': 'NCBITaxon:10116',
    'MGI': 'NCBITaxon:10090',
    'ZFIN': 'NCBITaxon:7955',
    'WB': 'NCBITaxon:6239',
    'SGD': 'NCBITaxon:559292',
    'FB': 'NCBITaxon:7227',

}


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
    
    # Determine correct prefix based on entity type
    if entity_type == 'gene':
        tp_prefix = f"tpg{id_prefix}"
    elif entity_type == 'protein':
        tp_prefix = f"tpp{id_prefix}"
    elif entity_type == 'gene_synonym':
        tp_prefix = f"tpgs{id_prefix}"
    elif entity_type == 'protein_synonym':
        tp_prefix = f"tpps{id_prefix}"
    elif entity_type == 'allele':
        tp_prefix = f"tpa{id_prefix}"
    elif entity_type == 'strain':
        tp_prefix = f"tps{id_prefix}"
    elif entity_type == 'fish':
        tp_prefix = f"tpf{id_prefix}"
    else:
        tp_prefix = f"tp{entity_type[0]}{id_prefix}"
    
    tp_root_id = f"{tp_prefix}:0000000"
    root_name = entity_type.replace('_', ' ').title()
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
                new_id = f"{tp_prefix}:{max_id:07d}"
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


def generate_entity_list_from_a_team_api(mod: str, entity_type: str, store_synonyms_separately: bool = False,
                                         all_uppercase_file_name: Optional[str] = None) -> None:
    """
    Generate entity list files using AGRCurationAPIClient.

    Args:
        mod: Model organism database (e.g., 'WB', 'MGI')
        entity_type: Type of entity to process ('gene', 'protein')
        store_synonyms_separately: Whether to also generate synonym files (only used for WB)
        all_uppercase_file_name: If provided, read entities from this file and generate uppercase versions
                               (used for WB proteins which are uppercase versions of genes)
    """
    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)
    now = time.asctime()
    
    # Handle uppercase file generation (e.g., WB proteins from genes)
    if all_uppercase_file_name:
        _generate_uppercase_from_source_file(all_uppercase_file_name, entity_type, id_prefix,
                                             species_name, filename_id, now, store_synonyms_separately)
        return
    
    api_client = _create_api_client()

    # Process entities
    entity_writer = _EntityFileWriter(entity_type, id_prefix, species_name, filename_id, now)
    # Only WB uses separate synonym files
    synonym_writer = (_EntityFileWriter(f"{entity_type}_synonym", id_prefix, species_name, filename_id, now)
                      if store_synonyms_separately else None)

    try:
        _process_entities_from_api(api_client, mod, entity_type, entity_writer, synonym_writer,
                                   taxon=MOD_TAXON_MAPPING.get(mod))
    finally:
        entity_writer.close()
        if synonym_writer:
            synonym_writer.close()


def update_entity_list_from_ateam_api(mod: str, entity_type: str) -> None:
    """
    Update existing entity list files with recent changes using AGRCurationAPIClient.
    Only processes entities updated in the last 2 months.

    For genes, synonyms are updated too: WB synonym changes are applied to the
    separate gene_synonym file, and other MODs' synonym changes are applied to the
    main gene file (mirroring the full-generation routing).

    Args:
        mod: Model organism database (e.g., 'WB', 'MGI')
        entity_type: Type of entity to process ('gene', 'allele', 'fish')
    """
    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)
    api_client = _create_api_client()

    # Collect recently updated entities (and, for genes, their synonyms)
    new_entities: Set[str] = set()
    obsolete_entities: Set[str] = set()
    new_synonyms: Set[str] = set()
    obsolete_synonyms: Set[str] = set()

    try:
        _collect_updated_entities(api_client, mod, entity_type, new_entities, obsolete_entities,
                                  new_synonyms, obsolete_synonyms)
    except Exception as e:
        print(f"Error collecting updated entities: {e}")
        return

    # WB keeps gene synonyms in a separate file; every other MOD folds them into
    # the main gene file (mirrors the full-generation routing).
    wb_separate_synonyms = mod == 'WB' and entity_type == 'gene'
    if entity_type in ('gene', 'protein') and not wb_separate_synonyms:
        new_entities |= new_synonyms
        obsolete_entities |= obsolete_synonyms
        new_synonyms.clear()
        obsolete_synonyms.clear()

    if not (new_entities or obsolete_entities or new_synonyms or obsolete_synonyms):
        print(f"No updated {entity_type} entities found for {mod}")
        return

    # Update the existing OBO file
    entity_list_file = f"{entity_type}_{filename_id}.obo"
    curr_entity_list_file = f"/data/textpresso/obofiles4production/{entity_list_file}"

    if new_entities or obsolete_entities:
        try:
            process_entities(curr_entity_list_file, entity_list_file, new_entities, obsolete_entities,
                             entity_type, id_prefix, species_name)
            print(f"Updated {entity_list_file}: {len(new_entities)} new, {len(obsolete_entities)} obsolete")
        except Exception as e:
            print(f"Error updating entity file: {e}")

    # WB: apply gene synonym changes to the separate gene_synonym file.
    if wb_separate_synonyms and (new_synonyms or obsolete_synonyms):
        synonym_type = f"{entity_type}_synonym"
        synonym_file = f"{synonym_type}_{filename_id}.obo"
        curr_synonym_file = f"/data/textpresso/obofiles4production/{synonym_file}"
        try:
            process_entities(curr_synonym_file, synonym_file, new_synonyms, obsolete_synonyms,
                             synonym_type, id_prefix, species_name)
            print(f"Updated {synonym_file}: {len(new_synonyms)} new, {len(obsolete_synonyms)} obsolete")
        except Exception as e:
            print(f"Error updating synonym file: {e}")


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
                               entity_writer: '_EntityFileWriter', synonym_writer: Optional['_EntityFileWriter'],
                               taxon: str = None) -> None:
    """Process entities from API with pagination."""
    current_page = 0
    found_synonyms: Set[str] = set()

    # The db data source used for the gene fetch returns symbol-only records with no
    # synonyms, so fetch synonyms separately from the API path and index them by
    # primaryExternalId. They are merged onto the db genes in _process_single_entity.
    gene_synonyms_map: dict[str, Any] = {}
    if entity_type in ['gene', 'protein']:
        gene_synonyms_map = _fetch_gene_synonyms_map(api_client, mod, taxon)

    while True:
        try:
            entities = _fetch_entities_page(api_client=api_client, mod=mod, entity_type=entity_type,
                                            page=current_page, taxon=taxon)
            if not entities:
                print(f"No entities returned for {entity_type} page {current_page}")
                break

            for entity in entities:
                if _should_skip_entity(entity):
                    continue

                _process_single_entity(entity, entity_type, mod, entity_writer, synonym_writer,
                                       found_synonyms, gene_synonyms_map)

            current_page += 1
            print(f"Page {current_page}: Entities: {entity_writer.records_count}, "
                  f"Synonyms: {synonym_writer.records_count if synonym_writer else 0}")

            if len(entities) == 0:
                break

        except Exception as e:
            print(f"Error fetching page {current_page}: {e}")
            import traceback
            traceback.print_exc()
            break


def _fetch_entities_page(api_client: AGRCurationAPIClient, mod: str, entity_type: str, page: int, updated_after=None,
                         taxon: str = None) -> list[Any]:
    """Fetch a single page of entities from the API."""
    if entity_type in ['gene', 'protein']:
        # Use the DB data source, translating this loop's `page` counter into the
        # `offset` the db path paginates by (offset = page * PAGE_LIMIT). This
        # mirrors the WB allele db call below and returns gene records (SO
        # gene-type filtered, so non-gene sequence features are excluded) for
        # every MOD that generates genes (WB, MGI, ZFIN, FB, SGD).
        #
        # `taxon` is required by the db path and is what it filters on
        # (data_provider and updated_after are ignored there). `include_obsolete`
        # is False so obsolete genes are excluded at the source and never reach
        # the output files. The 2-month date filtering for the incremental update
        # path is applied client-side in _collect_updated_entities.
        return api_client.get_genes(
            taxon=taxon,
            limit=PAGE_LIMIT,
            offset=page * PAGE_LIMIT,
            include_obsolete=False,
            data_source='db'
        )
    elif entity_type == 'allele':
        # WB extraction subset: force DB + correct params
        if mod == 'WB':
            return api_client.get_alleles(
                taxon='NCBITaxon:6239',
                limit=PAGE_LIMIT,
                offset=page * PAGE_LIMIT,
                wb_extraction_subset=True,
                data_source='db'
            )
        # other MODs: use normal API/GraphQL path
        return api_client.get_alleles(data_provider=mod, limit=PAGE_LIMIT, page=page, updated_after=updated_after)
    elif entity_type == 'fish':
        return api_client.get_agms(data_provider=mod, subtype="fish", limit=PAGE_LIMIT, page=page,
                                   updated_after=updated_after)
    return []


def _get_entity_primary_id(entity: Any) -> Optional[str]:
    """Return an entity's primary identifier (primaryExternalId, falling back to curie)."""
    for attr in ('primaryExternalId', 'primary_external_id', 'curie'):
        value = getattr(entity, attr, None)
        if value:
            return value
    return None


def _fetch_gene_synonyms_map(api_client: AGRCurationAPIClient, mod: str,
                             taxon: Optional[str]) -> dict[str, Any]:
    """
    Build a {primaryExternalId: geneSynonyms} map from the REST API path.

    The db data source used for the main gene fetch returns symbol-only records, so
    synonyms have to come from the API path, which returns full gene records with
    `geneSynonyms`. The API path also returns non-gene sequence features, but those
    are harmless here: only genes from the db set are ever looked up in this map.
    """
    synonyms_map: dict[str, Any] = {}
    page = 0
    while True:
        try:
            genes = api_client.get_genes(
                data_provider=mod,
                taxon=taxon,
                limit=PAGE_LIMIT,
                page=page,
                include_obsolete=False,
                data_source='api'
            )
        except Exception as e:
            print(f"Error fetching gene synonyms page {page}: {e}")
            break

        if not genes:
            break

        for gene in genes:
            synonyms = getattr(gene, 'geneSynonyms', None) or getattr(gene, 'gene_synonyms', None)
            if not synonyms:
                continue
            key = _get_entity_primary_id(gene)
            if key:
                synonyms_map[key] = synonyms

        # The REST API filters obsolete records client-side, so a page can hold fewer
        # than PAGE_LIMIT results while more pages remain. Keep paginating until an
        # empty page is returned (checked at the top of the loop).
        page += 1

    print(f"Fetched synonyms for {len(synonyms_map)} genes from API for {mod}")
    return synonyms_map


def _collect_updated_entities(api_client: AGRCurationAPIClient, mod: str, entity_type: str,
                              new_entities: Set[str], obsolete_entities: Set[str],
                              new_synonyms: Optional[Set[str]] = None,
                              obsolete_synonyms: Optional[Set[str]] = None) -> None:
    """
    Collect recently updated entities (within last 2 months) from the API.

    For genes/proteins this uses the REST API path rather than the symbol-only db
    path used for full generation: the API path supports `updated_after` and returns
    both date fields and `geneSynonyms`, which the db path does not. Gene synonyms are
    collected into new_synonyms/obsolete_synonyms when those sets are provided.

    Note: obsolete/new is decided per record; a record flagged obsolete or internal
    contributes its name (and synonyms) to the obsolete sets so they are removed.
    """
    current_page = 0
    records_processed = 0
    current_date = datetime.now()
    date_two_months_ago = (current_date - relativedelta(months=2)).isoformat()

    print(f"Collecting {entity_type} entities updated since {date_two_months_ago}")

    while True:
        try:
            if entity_type in ('gene', 'protein'):
                # API path: supports updated_after and returns synonyms + date fields.
                entities = api_client.get_genes(
                    data_provider=mod,
                    taxon=MOD_TAXON_MAPPING.get(mod),
                    limit=PAGE_LIMIT,
                    page=current_page,
                    updated_after=date_two_months_ago,
                    include_obsolete=True,
                    data_source='api'
                )
            else:
                entities = _fetch_entities_page(api_client=api_client, mod=mod, entity_type=entity_type,
                                                page=current_page, updated_after=date_two_months_ago,
                                                taxon=MOD_TAXON_MAPPING.get(mod))
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

                # Obsolete/internal records feed the removal sets; others feed the add sets.
                is_obsolete = _should_skip_entity(entity)

                entity_name = _get_entity_name_from_api_entity(entity, entity_type, mod)
                if entity_name:
                    (obsolete_entities if is_obsolete else new_entities).add(entity_name)

                # Collect gene synonyms when requested
                if entity_type in ('gene', 'protein') and new_synonyms is not None \
                        and obsolete_synonyms is not None:
                    for synonym_name in _get_gene_synonym_names(entity, mod):
                        (obsolete_synonyms if is_obsolete else new_synonyms).add(synonym_name)

            current_page += 1
            print(f"Page {current_page}: Processed {records_processed} entities, "
                  f"New: {len(new_entities)}, Obsolete: {len(obsolete_entities)}, "
                  f"New synonyms: {len(new_synonyms) if new_synonyms is not None else 0}, "
                  f"Obsolete synonyms: {len(obsolete_synonyms) if obsolete_synonyms is not None else 0}")

            # The REST API filters obsolete records client-side, so a short page does
            # not signal the end; keep going until an empty page (checked at the top).

        except Exception as e:
            print(f"Error fetching page {current_page}: {e}")
            break


def _get_entity_name_from_api_entity(entity: Any, entity_type: str, mod: str) -> Optional[str]:
    """Extract entity name from API entity object."""
    entity_name = None

    if entity_type == 'gene':
        entity_symbol = getattr(entity, 'geneSymbol', None) or getattr(entity, 'gene_symbol', None)
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


def _get_gene_synonym_names(entity: Any, mod: str) -> list[str]:
    """Extract formatted gene synonym names from an API gene entity."""
    synonyms = getattr(entity, 'geneSynonyms', None) or getattr(entity, 'gene_synonyms', None)
    names: list[str] = []
    if synonyms:
        for synonym in synonyms:
            synonym_name = get_name_from_entity(synonym)
            if synonym_name:
                names.append(_apply_mod_formatting(synonym_name, mod, 'gene'))
    return names


def _should_skip_entity(entity: Any) -> bool:
    """Check if entity should be skipped (obsolete or internal)."""
    return ((hasattr(entity, 'obsolete') and entity.obsolete) or
            (hasattr(entity, 'internal') and entity.internal))


def _process_single_entity(entity: Any, entity_type: str, mod: str,
                           entity_writer: '_EntityFileWriter',
                           synonym_writer: Optional['_EntityFileWriter'],
                           found_synonyms: Set[str],
                           gene_synonyms_map: Optional[dict[str, Any]] = None) -> None:
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
        entity_symbol = entity.agmFullName

    entity_name = get_name_from_entity(entity_symbol)

    if entity_name:
        formatted_name = _apply_mod_formatting(entity_name, mod, entity_type)
        entity_writer.write_entity(formatted_name)

    # Process synonyms
    synonyms = None

    # Get synonyms based on entity type
    if entity_type in ['gene', 'protein']:
        if hasattr(entity, 'geneSynonyms'):
            synonyms = entity.geneSynonyms
        elif hasattr(entity, 'gene_synonyms'):
            synonyms = entity.gene_synonyms
        # The db data source omits synonyms; fall back to the API-derived map,
        # keyed by primaryExternalId.
        if not synonyms and gene_synonyms_map:
            synonyms = gene_synonyms_map.get(_get_entity_primary_id(entity))
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
                
                # For WB, write to separate synonym file; for others, write to main file
                if synonym_writer:
                    # separate synonym file
                    synonym_writer.write_entity(formatted_synonym)
                else:
                    # write synonym to main entity file with same prefix
                    entity_writer.write_entity(formatted_synonym)


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
        elif entity_type == 'gene':
            self.filename = f"{entity_type}_{filename_id}.obo"
            self.tp_prefix = f"tpg{id_prefix}"
            self.root_name = entity_type.capitalize()
        elif entity_type == 'protein':
            self.filename = f"{entity_type}_{filename_id}.obo"
            self.tp_prefix = f"tpp{id_prefix}"
            self.root_name = entity_type.capitalize()
        elif entity_type == 'protein_synonym':
            self.filename = f"protein_synonym_{filename_id}.obo"
            self.tp_prefix = f"tpps{id_prefix}"
            self.root_name = "Protein Synonym"
        elif entity_type == 'allele':
            self.filename = f"{entity_type}_{filename_id}.obo"
            self.tp_prefix = f"tpa{id_prefix}"
            self.root_name = entity_type.capitalize()
        elif entity_type == 'strain':
            self.filename = f"{entity_type}_{filename_id}.obo"
            self.tp_prefix = f"tps{id_prefix}"
            self.root_name = entity_type.capitalize()
        elif entity_type == 'fish':
            self.filename = f"{entity_type}_{filename_id}.obo"
            self.tp_prefix = f"tpf{id_prefix}"
            self.root_name = entity_type.capitalize()
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