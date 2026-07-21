import os
import time
import logging
import requests
import pandas as pd
from tqdm import tqdm
from Bio import Entrez
from requests.exceptions import RequestException

# ========================
# SETTINGS
# ========================


ncbi_api_key = os.environ.get("ncbi_api_key")
Entrez.email = os.environ.get("email")
Entrez.api_key = ncbi_api_key

MAX_ARTICLES = 100
SLEEP_TIME = 0.5  # polite delay between downloads
OUTPUT_DIR = "./pmc_htmls"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def build_query():
    """Constructs the PubMed search query."""
    disease_terms = [
        "lung cancer",
        "lung carcinoma",
        "NSCLC",
        "SCLC",
        "mesothelioma",
        "pulmonary carcinoma",
        "bronchogenic carcinoma"
    ]
    disease_query = " OR ".join(f'"{term}"[Title/Abstract]' for term in disease_terms)
    return (
        f'({disease_query}) AND '
        '"case reports"[Publication Type] AND '
        'free full text[Filter] AND '
        '("2019/01/01"[Date - Publication] : "3000"[Date - Publication])'
    )

def search_pubmed(query):
    """Searches PubMed and returns search results with WebEnv and QueryKey."""
    handle = Entrez.esearch(db="pubmed", term=query, retmax=MAX_ARTICLES, usehistory="y")
    search_results = Entrez.read(handle)
    handle.close()
    return search_results

def fetch_metadata(query_key, webenv):
    """Fetches article metadata using Entrez efetch."""
    handle = Entrez.efetch(db="pubmed", query_key=query_key, webenv=webenv, retmode="xml", retmax=MAX_ARTICLES)
    records = Entrez.read(handle)
    handle.close()
    return records

def extract_articles(records):
    """Extracts metadata for each article into a list of dictionaries."""
    articles = []
    for article in records.get("PubmedArticle", []):
        pmid = article["MedlineCitation"]["PMID"]
        title = article["MedlineCitation"]["Article"]["ArticleTitle"]

        authors_list = []
        authors = article["MedlineCitation"]["Article"].get("AuthorList", [])
        for author in authors:
            if "LastName" in author and "Initials" in author:
                authors_list.append(f"{author['LastName']} {author['Initials']}")

        journal = article["MedlineCitation"]["Article"]["Journal"]["Title"]
        pub_date = extract_pub_date(article)
        abstract = extract_abstract(article)
        pmc_id = extract_pmc_id(article)

        if pmc_id:
            url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/?report=classic"
            citation = build_citation(authors_list, title, journal, pub_date)
            articles.append({
                "PMID": pmid,
                "PMC_ID": pmc_id,
                "Title": title,
                "Journal": journal,
                "PublicationDate": pub_date,
                "Authors": "; ".join(authors_list),
                "Abstract": abstract,
                "URL": url,
                "Citation": citation
            })
    return articles

def extract_pub_date(article):
    """Extracts publication date from article."""
    pub_date_info = article["MedlineCitation"]["Article"]["Journal"]["JournalIssue"].get("PubDate", {})
    if "Year" in pub_date_info:
        return pub_date_info["Year"]
    return pub_date_info.get("MedlineDate", "n.d.")

def extract_abstract(article):
    """Extracts abstract text if available."""
    try:
        return article["MedlineCitation"]["Article"]["Abstract"]["AbstractText"][0]
    except (KeyError, IndexError):
        return None

def extract_pmc_id(article):
    """Extracts PMC ID from ArticleIdList."""
    article_ids = article["PubmedData"].get("ArticleIdList", [])
    for id_item in article_ids:
        if id_item.attributes.get("IdType") == "pmc":
            return str(id_item)
    return None

def build_citation(authors_list, title, journal, pub_date):
    """Formats citation string."""
    if authors_list:
        first_author = authors_list[0].split()[0]
        et_al = "et al." if len(authors_list) > 1 else ""
        return f"{first_author} {et_al}. {title}. {journal}. {pub_date}."
    return f"{title}. {journal}. {pub_date}."

def sanitize_filename(title, pmc_id):
    """Sanitizes file name for saving HTML."""
    safe_title = "".join(c if c.isalnum() else "_" for c in title)[:80]
    return f"{safe_title}_{pmc_id}.html"

def download_htmls(articles, output_dir, headers, sleep_time):
    """Downloads HTML files and records their local file paths."""
    os.makedirs(output_dir, exist_ok=True)
    for article in tqdm(articles, desc="📥 Downloading HTMLs"):
        url = article["URL"]
        filename = sanitize_filename(article["Title"], article["PMC_ID"])
        filepath = os.path.join(output_dir, filename)
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            with open(filepath, "w", encoding="utf-8") as f_out:
                f_out.write(response.text)
            article["HTML_FILE"] = os.path.abspath(filepath)  # ✅ record absolute path
        except RequestException as e:
            logging.warning(f"⚠️ Failed to download {url}: {e}")
            article["HTML_FILE"] = None
        time.sleep(sleep_time)

def main():
    """Main execution function."""
    query = build_query()
    logging.info(f"🔎 Query: {query}")
    search_results = search_pubmed(query)
    webenv = search_results["WebEnv"]
    query_key = search_results["QueryKey"]
    total_found = int(search_results["Count"])
    logging.info(f"🔎 Found {total_found} articles")

    records = fetch_metadata(query_key, webenv)
    articles = extract_articles(records)
    logging.info(f"✅ Valid articles with PMC ID: {len(articles)}")

    if len(articles) > MAX_ARTICLES:
        articles = articles[:MAX_ARTICLES]
        logging.info(f"⚠️ Capped to {MAX_ARTICLES} articles")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    download_htmls(articles, OUTPUT_DIR, headers, SLEEP_TIME)

    df = pd.DataFrame(articles)
    df.to_csv("expanded_lung_cancer_case_reports_2019_onward.csv", index=False)
    df.to_pickle("expanded_lung_cancer_case_reports_2019_onward.pkl")
    logging.info(f"✅ Saved metadata for {len(df)} articles (including HTML file paths)")

if __name__ == "__main__":
    main()
