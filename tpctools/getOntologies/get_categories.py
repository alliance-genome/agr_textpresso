"""
Main module for generating category data for AGR Textpresso.

This module orchestrates the processing of biological entities and ontologies
for text mining purposes. It has been refactored to separate concerns into
dedicated modules:

- entities.py: Functions for processing biological entities (genes, alleles, fish)
- ontology.py: Functions for downloading and processing ontologies
"""

import argparse

from get_sgd_specific_categories import create_obo_file  # type: ignore
from entities import (
    get_id_prefix_species_name,
    generate_entity_list_from_a_team_api,
    update_entity_list_from_ateam_api
)
from ontology import download_all_ontologies


def get_category_data(mod, download_all=False):
    """
    Generate category data for a given Model Organism Database (MOD).
    
    Args:
        mod: Model organism database identifier (e.g., 'WB', 'MGI', 'ZFIN')
        download_all: Whether to download all ontologies
    """
    id_prefix, species_name, filename_id = get_id_prefix_species_name(mod)

    if download_all:
        download_all_ontologies(mod, id_prefix)

    if mod == 'WB':
        generate_entity_list_from_a_team_api(mod, 'gene', store_synonyms_separately=True)
        # Generate proteins as uppercase versions of genes (no API call needed)
        generate_entity_list_from_a_team_api(mod, 'protein', store_synonyms_separately=True,
                                             all_uppercase_file_name=f'gene_{filename_id}.obo')
        # update_entity_list_from_ateam_api(mod, 'allele')
        generate_entity_list_from_a_team_api(mod, 'allele')
    elif mod == 'MGI':
        generate_entity_list_from_a_team_api(mod, 'gene')
    elif mod == 'ZFIN':
        generate_entity_list_from_a_team_api(mod, 'gene')
        generate_entity_list_from_a_team_api(mod, 'allele')
        generate_entity_list_from_a_team_api(mod, 'fish')
    elif mod == 'FB':
        generate_entity_list_from_a_team_api(mod, 'gene')
    elif mod == 'SGD':
        generate_entity_list_from_a_team_api(mod, 'gene')
        generate_entity_list_from_a_team_api(mod, 'allele')
        create_obo_file('tppsc', 'Protein', "protein_saccharomyces_cerevisiae.obo")
        create_obo_file('tpssc', 'Strain', "strain_saccharomyces_cerevisiae.obo")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mod', action='store', type=str, help='MOD to dump',
                        choices=['SGD', 'WB', 'FB', 'ZFIN', 'MGI', 'RGD', 'XB'], required=True)
    parser.add_argument('-a', '--all', action='store_true', help="download all ontologies")
    args = parser.parse_args()
    get_category_data(args.mod, args.all)
