from tpctools.utils import email_utils
from os import environ, path
import re
import sys

logfile = "/tmp/incremental_build.log"
# 12index.sh has already swapped the new index into place when the report is sent
indexCountFile = "/data/textpresso/luceneindex/cc.cfg"
count_pattern = re.compile(r"(Total staged PDF file\(s\)|Total new CAS-[12] count|Empty CAS-[12] count): (\d+)")
new_paper_pattern = re.compile(r"New paper: (\S+)")


def send_report(email_subject=None, email_message=None):

    if email_subject is None:
        MOD = environ.get('MOD', 'Unknown')
        email_subject = f"{MOD} Textpresso Incremental Build Report"
    if email_message is None:
        email_message = compose_message()
    email_utils.send_report(email_subject, email_message)


def compose_message():

    # incremental_build.sh prefixes every line with "[incremental_build <run id>] "
    counts = {}
    new_papers = []
    with open(logfile) as f:
        for line in f:
            count_match = count_pattern.search(line)
            if count_match:
                counts[count_match.group(1)] = count_match.group(2)
            paper_match = new_paper_pattern.search(line)
            if paper_match:
                new_papers.append(paper_match.group(1))

    total_indexed = None
    if path.exists(indexCountFile):
        with open(indexCountFile) as f:
            for line in f:
                total_indexed = line.strip().split(' ')[-1]

    rows = ""
    for (label, count) in [('PDF downloaded', counts.get('Total staged PDF file(s)')),
                           ('CAS-1 files generated', counts.get('Total new CAS-1 count')),
                           ('Empty CAS-1 files', counts.get('Empty CAS-1 count')),
                           ('CAS-2 files generated', counts.get('Total new CAS-2 count')),
                           ('Empty CAS-2 files', counts.get('Empty CAS-2 count')),
                           ('Total papers in index', total_indexed)]:
        if str(count).isdigit():
            rows = rows + f"<tr><th style='text-align:left' width='300'>{label}</th><td width='100'>{count}</td></tr>"
    email_message = "<table></tbody>" + rows + "</tbody></table>"
    email_message = email_message + "<p>The logfile is available at /tmp/incremental_build.log</p>"
    email_message = email_message + ("<p>The full-text files for the following papers have just been added to "
                                     "Textpresso.")
    email_message = email_message + "<p>" + "<br>".join(new_papers) + "<p>"
    return email_message


if __name__ == "__main__":
    subject = sys.argv[1] if len(sys.argv) > 1 else None
    message = sys.argv[2] if len(sys.argv) > 2 else None
    send_report(subject, message)
