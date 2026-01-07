import dns.resolver
from urllib.parse import urlparse
from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.table import Table
from concurrent.futures import ThreadPoolExecutor, as_completed
from os import system
import threading
import requests
import re
import time
import os

os.system("cls" if os.name == "nt" else "clear")
system("title " + "yuzu - Subdomain v2.0")


console = Console()
print_lock = threading.Lock()

logo = r"""
               __        __                      _     
   _______  __/ /_  ____/ /___  ____ ___  ____ _(_)___ 
  / ___/ / / / __ \/ __  / __ \/ __ `__ \/ __ `/ / __ \
 (__  ) /_/ / /_/ / /_/ / /_/ / / / / / / /_/ / / / / /
/____/\__,_/_.___/\__,_/\____/_/ /_/ /_/\__,_/_/_/ /_/ 

                    [v2.0] - yuzu 
                    
"""

hex_colors = ["#FF0080", "#FF00F7", "#6600FF", "#1E00FF"]


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def interpolate_color(start, end, t):
    t = t * t * (3 - 2 * t)
    return tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))

def gradient_text(text_str):
    """Applique un dégradé horizontal (gauche → droite) sur chaque ligne"""
    text = Text()
    rgbs = [hex_to_rgb(c) for c in hex_colors]
    segments = len(rgbs) - 1
    
    lines = text_str.split('\n')
    
    for line_idx, line in enumerate(lines):
        if line_idx > 0:
            text.append('\n')
        
        # Applique le dégradé sur chaque caractère de la ligne
        line_length = len(line)
        for i, char in enumerate(line):
            if line_length > 1:
                t = i / (line_length - 1)
            else:
                t = 0
            
            pos = t * segments
            idx = min(int(pos), segments - 1)
            rgb = interpolate_color(rgbs[idx], rgbs[idx + 1], pos - idx)
            text.append(char, style=f"rgb({rgb[0]},{rgb[1]},{rgb[2]})")
    
    return text

def banner(text):
    return Align.center(gradient_text(text))

def extract_domain(url):
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    parsed = urlparse(url)
    return parsed.netloc.lower().lstrip("www.")

def resolve_subdomain(sub, domain, found):
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 3

    full_domain = f"{sub}.{domain}"
    try:
        answers = resolver.resolve(full_domain, "A")
        ips = ", ".join(str(ip) for ip in answers)

        with print_lock:
            if full_domain not in found:
                found.add(full_domain)

    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
        pass
    except Exception:
        pass

def ct_logs(domain, found):
    console.print(gradient_text("\n[1/6] Certificate Transparency (crt.sh)..."))
    try:
        url = f"https://crt.sh/?q=%.{domain}&output=json"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for entry in data:
                name = entry.get("name_value", "")
                for sub in name.split("\n"):
                    sub = sub.strip().lower()
                    if sub.endswith(domain) and sub not in found:
                        with print_lock:
                            found.add(sub)
    except Exception as e:
        console.print(gradient_text(f"[!] CT Logs error: {e}"))


def dns_passive(domain, found):
    console.print(gradient_text("\n[2/6] DNS Passive (VirusTotal)..."))
    try:
        url = f"https://www.virustotal.com/ui/domains/{domain}/subdomains?limit=40"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("data", []):
                sub = item.get("id", "").lower()
                if sub.endswith(domain) and sub not in found:
                    with print_lock:
                        found.add(sub)
    except Exception as e:
        console.print(gradient_text(f"[!] VirusTotal error: {e}"))


def google_dork(domain, found):
    console.print(gradient_text("\n[3/6] Google Dorking..."))
    try:
        query = f"site:*.{domain}"
        url = f"https://www.google.com/search?q={query}&num=50"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        
        pattern = rf"https?://([a-z0-9\-\.]+\.{re.escape(domain)})"
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        
        for sub in set(matches):
            sub = sub.lower()
            if sub not in found:
                with print_lock:
                    found.add(sub)
    except Exception as e:
        console.print(gradient_text(f"[!] Google Dork error: {e}"))


def scrape_site(domain, found):
    console.print(gradient_text("\n[4/6] Scraping..."))
    try:
        url = f"https://{domain}"
        r = requests.get(url, timeout=10, allow_redirects=True)
        
        pattern = rf"https?://([a-z0-9\-\.]+\.{re.escape(domain)})"
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        
        for sub in set(matches):
            sub = sub.lower()
            if sub not in found:
                with print_lock:
                    found.add(sub)
    except Exception as e:
        console.print(gradient_text(f"[!] Scraping error: {e}"))


def permutations(domain, found):
    console.print(gradient_text("\n[5/6] Smart Permutations..."))
    
    base_subs = list(found)[:10]
    suffixes = ["-dev", "-test", "-staging", "-prod", "-api", "-v1", "-v2", "-internal"]
    
    perms = set()
    for sub in base_subs:
        prefix = sub.replace(f".{domain}", "")
        for suffix in suffixes:
            perms.add(f"{prefix}{suffix}.{domain}")
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        tasks = [
            executor.submit(resolve_subdomain, p.replace(f".{domain}", ""), domain, found)
            for p in perms
        ]
        for _ in as_completed(tasks):
            pass


def reverse_dns(domain, found):
    console.print(gradient_text("\n[6/6] Reverse DNS (ASN lookup)..."))
    try:
        answers = dns.resolver.resolve(domain, "A")
        ip = str(answers[0])
        
        url = f"https://ipinfo.io/{ip}/json"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            org = data.get("org", "")
            console.print(gradient_text(f"[ASN] {domain} -> {ip} ({org})"))
            
    except Exception as e:
        console.print(gradient_text(f"[!] Reverse DNS error: {e}"))


def display_results(domain, found):
    console.print("\n")
    console.print(gradient_text(f"{'='*70}"))
    console.print(gradient_text(f"           RÉSULTATS POUR : {domain}"))
    console.print(gradient_text(f"{'='*70}\n"))
    
    if not found:
        console.print(gradient_text("[!] Aucun sous-domaine trouvé"))
        return
    
    table = Table(show_header=True, header_style="bold magenta", border_style="cyan")
    table.add_column("N°", style="dim", width=6)
    table.add_column("Sous-domaine", style="cyan")
    
    for idx, subdomain in enumerate(sorted(found), 1):
        table.add_row(str(idx), subdomain)
    
    console.print(table)
    console.print(gradient_text(f"\n[✓] TOTAL : {len(found)} sous-domaines trouvés"))
    console.print(gradient_text(f"{'='*70}\n"))


def run_scan_by_yuzu(domain):
    found_subdomains = set()

    ct_logs(domain, found_subdomains)
    time.sleep(1)

    dns_passive(domain, found_subdomains)
    time.sleep(1)

    google_dork(domain, found_subdomains)
    time.sleep(1)

    scrape_site(domain, found_subdomains)
    time.sleep(1)

    console.print(gradient_text("\n[BONUS] DNS Brute Force..."))
    subdomains = [
        "www","mail","ftp","api","dev","test","admin","blog","shop","store","app","cdn",
        "static","img","images","assets","media","api-v1","api-v2","beta","stage",
        "staging","prod","production","sandbox","internal","private","auth","login",
        "portal","dashboard","panel","control","cpanel","webmail","smtp","imap","pop",
        "ns1","ns2","dns","db","database","sql","mysql","redis","cache","git","gitlab",
        "github","ci","jenkins","monitor","status","metrics","grafana","kibana",
        "mobile","m","ios","android","backup","demo","secure","payment","checkout"
    ]

    with ThreadPoolExecutor(max_workers=30) as executor:
        tasks = [
            executor.submit(resolve_subdomain, sub, domain, found_subdomains)
            for sub in subdomains
        ]
        for _ in as_completed(tasks):
            pass

    permutations(domain, found_subdomains)

    reverse_dns(domain, found_subdomains)
    
    return found_subdomains


def main():
    while True:
        console.print("\n")
        console.print(banner(logo))
        console.print("\n")

        console.print(gradient_text("Website url ⭢ "), end="")
        user_input = input().strip()
        
        if not user_input:
            continue
            
        domain = extract_domain(user_input)

        console.print(gradient_text(f"\n[+] Domaine détecté : {domain}"))
        console.print(gradient_text("[+] Démarrage...\n"))

        found = run_scan_by_yuzu(domain)
        
        display_results(domain, found)
        
        console.print(gradient_text("\nAppuyez sur Entrée pour continuer..."), end="")
        input()

if __name__ == "__main__":
    main()

# MERCI AU SKID DE PAS CTRL C + CTRL V