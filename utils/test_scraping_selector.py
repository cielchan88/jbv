"""
Helper Script: Test Trading Economics Selectors
================================================

Script untuk test dan find selector yang tepat dari Trading Economics.

Usage:
    python utils/test_scraping_selector.py --url https://tradingeconomics.com/indonesia/currency
    python utils/test_scraping_selector.py --indicator USD_IDR

Author: Tim APUVA
Date: 2025-11-19
"""

import requests
from bs4 import BeautifulSoup
import argparse
from typing import Optional, List
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

INDICATORS_URL = {
    'USD_IDR': 'https://tradingeconomics.com/indonesia/currency',
    'Oil_Price_Brent': 'https://tradingeconomics.com/commodity/brent',
    'Gold_Price': 'https://tradingeconomics.com/commodity/gold',
    'US_Treasury_10Y': 'https://tradingeconomics.com/united-states/government-bond-yield',
}


def fetch_page(url: str) -> Optional[str]:
    """Fetch HTML page"""
    try:
        logger.info(f"Fetching: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        logger.info(f"✓ Success (status {response.status_code})")
        return response.text
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return None


def find_value_candidates(html: str) -> List[dict]:
    """
    Find potential value elements in HTML.

    Returns list of candidates with their selector and value.
    """
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []

    # Strategy 1: Look for specific IDs containing numbers
    logger.info("\n--- Strategy 1: IDs with numbers ---")
    for elem in soup.find_all(id=True):
        text = elem.get_text().strip()
        if text and any(char.isdigit() for char in text):
            # Check if it looks like a number (contains digit and possibly decimal/comma)
            if len(text) < 20 and ('.' in text or ',' in text or text.replace('.', '').replace(',', '').isdigit()):
                candidates.append({
                    'type': 'id',
                    'selector': f"#{elem['id']}",
                    'value': text,
                    'tag': elem.name
                })
                logger.info(f"  Found: #{elem['id']} = '{text}'")

    # Strategy 2: Look for classes containing 'value', 'price', 'rate'
    logger.info("\n--- Strategy 2: Classes with keywords ---")
    keywords = ['value', 'price', 'rate', 'last', 'actual']
    for keyword in keywords:
        for elem in soup.find_all(class_=lambda x: x and keyword in x.lower()):
            text = elem.get_text().strip()
            if text and any(char.isdigit() for char in text):
                if len(text) < 20:
                    class_name = elem.get('class', [''])[0]
                    candidates.append({
                        'type': 'class',
                        'selector': f".{class_name}",
                        'value': text,
                        'tag': elem.name
                    })
                    logger.info(f"  Found: .{class_name} = '{text}'")

    # Strategy 3: Look for table cells with numbers
    logger.info("\n--- Strategy 3: Table cells ---")
    for td in soup.find_all('td'):
        text = td.get_text().strip()
        if text and any(char.isdigit() for char in text):
            if len(text) < 20 and ('.' in text or ',' in text):
                # Try to find unique identifier
                parent_attrs = []
                if td.get('class'):
                    parent_attrs.append(f"class='{td.get('class')[0]}'")
                if td.get('id'):
                    parent_attrs.append(f"id='{td.get('id')}'")

                selector = f"td[{parent_attrs[0]}]" if parent_attrs else "td"
                candidates.append({
                    'type': 'table',
                    'selector': selector,
                    'value': text,
                    'tag': 'td'
                })
                logger.info(f"  Found: {selector} = '{text}'")

    # Strategy 4: Look for spans with data attributes
    logger.info("\n--- Strategy 4: Spans with data attributes ---")
    for span in soup.find_all('span', attrs={'data-value': True}):
        value = span.get('data-value')
        selector_parts = []
        if span.get('id'):
            selector_parts.append(f"#{span['id']}")
        elif span.get('class'):
            selector_parts.append(f".{span['class'][0]}")

        selector = selector_parts[0] if selector_parts else "span[data-value]"
        candidates.append({
            'type': 'data-attr',
            'selector': selector,
            'value': value,
            'tag': 'span'
        })
        logger.info(f"  Found: {selector} = '{value}'")

    return candidates


def test_selector(html: str, selector: str) -> Optional[str]:
    """Test a specific CSS selector"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        elem = soup.select_one(selector)
        if elem:
            return elem.get_text().strip()
        return None
    except Exception as e:
        logger.error(f"Error testing selector '{selector}': {e}")
        return None


def save_html_sample(html: str, filename: str = 'trading_economics_sample.html'):
    """Save HTML sample for manual inspection"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info(f"\n✓ HTML saved to: {filename}")
    logger.info("  Open in browser to inspect structure")


def main():
    parser = argparse.ArgumentParser(description='Test Trading Economics selectors')
    parser.add_argument('--url', type=str, help='URL to test')
    parser.add_argument('--indicator', type=str, choices=INDICATORS_URL.keys(),
                       help='Indicator name (USD_IDR, Oil_Price_Brent, etc)')
    parser.add_argument('--selector', type=str, help='Test specific selector')
    parser.add_argument('--save-html', action='store_true',
                       help='Save HTML to file for manual inspection')

    args = parser.parse_args()

    # Determine URL
    if args.indicator:
        url = INDICATORS_URL[args.indicator]
        logger.info(f"Testing indicator: {args.indicator}")
    elif args.url:
        url = args.url
    else:
        logger.error("Please specify --url or --indicator")
        return

    # Fetch page
    html = fetch_page(url)
    if not html:
        return

    # Save HTML if requested
    if args.save_html:
        save_html_sample(html)

    # Test specific selector
    if args.selector:
        logger.info(f"\n{'='*70}")
        logger.info(f"Testing selector: {args.selector}")
        logger.info(f"{'='*70}")
        value = test_selector(html, args.selector)
        if value:
            logger.info(f"✓ Found value: '{value}'")
        else:
            logger.info(f"✗ No match found")
        return

    # Find candidates
    logger.info(f"\n{'='*70}")
    logger.info("Finding value candidates...")
    logger.info(f"{'='*70}")

    candidates = find_value_candidates(html)

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info("SUMMARY")
    logger.info(f"{'='*70}")
    logger.info(f"Total candidates found: {len(candidates)}")

    if candidates:
        logger.info("\nTop candidates:")
        for i, cand in enumerate(candidates[:10], 1):
            logger.info(f"  {i}. {cand['selector']}")
            logger.info(f"     Value: '{cand['value']}'")
            logger.info(f"     Type: {cand['type']}, Tag: {cand['tag']}")
    else:
        logger.info("\n⚠ No candidates found. Try --save-html for manual inspection.")

    # Recommendations
    logger.info(f"\n{'='*70}")
    logger.info("NEXT STEPS")
    logger.info(f"{'='*70}")
    logger.info("1. Review candidates above")
    logger.info("2. Test specific selector:")
    logger.info(f"   python {__file__} --url {url} --selector 'YOUR_SELECTOR'")
    logger.info("3. Update etl/scrape_trading_economics.py with correct selector")
    logger.info("4. Or save HTML for manual inspection:")
    logger.info(f"   python {__file__} --url {url} --save-html")


if __name__ == "__main__":
    main()
