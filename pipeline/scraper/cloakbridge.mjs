/**
 * CloakBrowser Bridge for Latinos.org Pipeline
 *
 * This script is called from Python to scrape JS-heavy sites (Univision, Telemundo).
 * It launches CloakBrowser, navigates to target URLs, and extracts article data.
 *
 * Usage:
 *   node cloakbridge.mjs <command> <config_json>
 *
 * Commands:
 *   "scrape_links"   — Extract article links from a listing page
 *   "scrape_article" — Extract full content from an article page
 *
 * Output: JSON array printed to stdout
 */

import * as cloakbrowser from 'cloakbrowser';

const COMMAND = process.argv[2];
const CONFIG = JSON.parse(process.argv[3] || '{}');

async function main() {
    let browser;
    try {
        browser = await cloakbrowser.launch({
            headless: true,
            timeout: 60000,
        });

        if (COMMAND === 'scrape_links') {
            const result = await scrapeLinks(browser, CONFIG);
            console.log(JSON.stringify(result));
        } else if (COMMAND === 'scrape_article') {
            const result = await scrapeArticle(browser, CONFIG);
            console.log(JSON.stringify(result));
        } else {
            console.log(JSON.stringify({ error: `Unknown command: ${COMMAND}` }));
        }
    } catch (e) {
        console.log(JSON.stringify({ error: e.message, stack: e.stack }));
    } finally {
        if (browser) await browser.close();
    }
}

/**
 * Scrape article links from a listing/category page.
 * CONFIG: { url, link_selector, category_hint }
 */
async function scrapeLinks(browser, config) {
    const page = await browser.newPage();
    const results = [];

    try {
        await page.goto(config.url, {
            waitUntil: 'domcontentloaded',
            timeout: 45000,
        });

        // Wait for content to render
        await page.waitForTimeout(5000);

        // Scroll down to trigger lazy loading
        await autoScroll(page);

        // Extract article links
        const links = await page.evaluate((selector) => {
            const anchors = document.querySelectorAll(selector);
            const seen = new Set();
            const results = [];

            for (const a of anchors) {
                const href = a.href;
                if (!href || seen.has(href)) continue;
                if (href.includes('#') || href.includes('?')) continue;
                seen.add(href);

                // Get associated text/headline
                const h = a.querySelector('h1, h2, h3, h4, .title, .headline');
                const text = h ? h.textContent.trim() : a.textContent.trim().substring(0, 200);
                const img = a.querySelector('img');
                const imgSrc = img ? (img.src || img.getAttribute('data-src') || '') : '';

                results.push({ url: href, title: text, image_url: imgSrc });
            }
            return results;
        }, config.link_selector || 'article a');

        for (const link of links) {
            results.push({
                url: link.url,
                title: link.title,
                image_url: link.image_url,
                category_hint: config.category_hint || '',
            });
        }

    } catch (e) {
        results.push({ error: e.message });
    } finally {
        await page.close();
    }

    return results;
}

/**
 * Scrape full content from an article page.
 * CONFIG: { url, title_selector, body_selector, author_selector, date_selector, image_selector, strip_selectors }
 */
async function scrapeArticle(browser, config) {
    const page = await browser.newPage();

    try {
        await page.goto(config.url, {
            waitUntil: 'domcontentloaded',
            timeout: 45000,
        });

        // Wait for article content to render
        await page.waitForTimeout(3000);

        // Remove unwanted elements (ads, related content, etc.)
        if (config.strip_selectors) {
            for (const sel of config.strip_selectors) {
                await page.evaluate((s) => {
                    document.querySelectorAll(s).forEach(el => el.remove());
                }, sel);
            }
        }

        // Extract structured data
        const data = await page.evaluate((cfg) => {
            const getText = (sel) => {
                const el = document.querySelector(sel);
                return el ? el.textContent.trim() : '';
            };

            const title = getText(cfg.title_selector || 'h1');

            // Body: try to get clean text paragraphs
            const bodyEl = document.querySelector(cfg.body_selector || 'article');
            let bodyHtml = '';
            let bodyText = '';

            if (bodyEl) {
                const paragraphs = bodyEl.querySelectorAll('p, h2, h3, blockquote, li');
                const parts = [];
                for (const p of paragraphs) {
                    const text = p.textContent.trim();
                    if (text.length > 20) {  // Skip short snippets
                        if (p.tagName === 'H2' || p.tagName === 'H3') {
                            parts.push(`\n## ${text}\n`);
                        } else if (p.tagName === 'BLOCKQUOTE') {
                            parts.push(`\n> ${text}\n`);
                        } else {
                            parts.push(text);
                        }
                    }
                }
                bodyText = parts.join('\n\n');
                bodyHtml = bodyEl.innerHTML;
            }

            // Author
            const author = getText(cfg.author_selector || '.author, .byline');

            // Date
            const dateEl = document.querySelector(cfg.date_selector || 'time');
            const dateStr = dateEl ?
                (dateEl.getAttribute('datetime') || dateEl.textContent.trim()) : '';

            // Image
            const imgEl = document.querySelector(cfg.image_selector || 'article img');
            const imageUrl = imgEl ?
                (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
            const imageAlt = imgEl ? (imgEl.alt || '') : '';

            // Meta description
            const metaDesc = document.querySelector('meta[name="description"]');
            const metaDescription = metaDesc ? metaDesc.getAttribute('content') : '';

            return {
                title,
                body_text: bodyText,
                body_html: bodyHtml,
                author,
                publish_date: dateStr,
                image_url: imageUrl,
                image_alt: imageAlt,
                meta_description: metaDescription,
                url: window.location.href,
            };
        }, config.content_config || {});

        return data;

    } catch (e) {
        return { error: e.message };
    } finally {
        await page.close();
    }
}

/**
 * Auto-scroll the page to trigger lazy loading.
 */
async function autoScroll(page) {
    await page.evaluate(async () => {
        await new Promise((resolve) => {
            let totalHeight = 0;
            const distance = 300;
            const timer = setInterval(() => {
                const scrollHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                totalHeight += distance;

                if (totalHeight >= scrollHeight - 100 || totalHeight > 5000) {
                    clearInterval(timer);
                    resolve();
                }
            }, 200);
        });
    });
}

main();
