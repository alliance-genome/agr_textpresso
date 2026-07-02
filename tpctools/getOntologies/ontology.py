"""
Ontology processing module for AGR Textpresso.

This module contains functions for downloading, processing, and managing
biological ontologies (GO, DOID, ChEBI, SO, etc.) for text mining purposes.
"""

import urllib.request
from typing import Optional

# current.geneontology.org (and at times purl.obolibrary.org) sit behind bot
# protection that returns HTTP 403 for the default "Python-urllib/x.y"
# User-Agent. Install a global opener presenting a browser-like User-Agent so
# every urlretrieve below (and any redirects it follows) is accepted.
_opener = urllib.request.build_opener()
_opener.addheaders = [(
    'User-Agent',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'
)]
urllib.request.install_opener(_opener)


def download_all_ontologies(mod: str, id_prefix: str) -> None:
    """Download and process all relevant ontologies for a given MOD."""
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


def remove_obsolete_terms(input_file_path: str, output_file_path: str) -> None:
    """Remove obsolete terms from an OBO file."""
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


def generate_flattened_ontology_file(obo_file: str, id_prefix: str) -> None:
    """Generate a flattened version of an ontology file for fast loading."""
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

    term_type = None
    with open(obo_file, 'r') as f, open(flattened_file, 'w') as fw:
        for count, line in enumerate(f, start=1):
            if count < 5:
                fw.write(line)
            elif count == 5:
                fw.write(f"\n[Term]\nid: {root_id}\nname: {root_term}\n\n")
            if line.strip().startswith("[") and line.strip().endswith("]"):
                term_type = line.strip()
            for text in ["[Term]", "id: ", "name: ", "def: ", "synonym: ", "xref: "]:
                if line.startswith(text):
                    fw.write(line)
            if count > 5 and line.strip() == '' and term_type == "[Term]":
                fw.write(f"is_a: {root_id} ! {root_term}\n\n")
            if line.startswith("[Typedef]"):
                break

    print(f"Flattened file created: {flattened_file}")