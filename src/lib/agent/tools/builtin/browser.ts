// Browser Tool - Real implementation using Puppeteer
import { Tool, ToolCall, ToolResult } from '../../types';

export const browserTool: Tool = {
  name: 'browser',
  description: 'Control a web browser to navigate pages, take screenshots, click elements, and extract information from websites.',
};

interface BrowserArgs {
  action: 'navigate' | 'screenshot' | 'click' | 'fill' | 'extract' | 'scroll' | 'get_html';
  url?: string;
  selector?: string;
  value?: string;
  extract_type?: 'text' | 'href' | 'src' | 'all';
  wait_for?: string;
}

// In-memory browser instance for the session
let browserInstance: any = null;
let pageInstance: any = null;

async function getBrowser() {
  if (!browserInstance) {
    const puppeteer = await import('puppeteer');
    browserInstance = await puppeteer.default.launch({
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--disable-gpu',
      ],
    });
  }
  return browserInstance;
}

async function getPage() {
  const browser = await getBrowser();
  if (!pageInstance) {
    pageInstance = await browser.newPage();
    // Set reasonable viewport
    await pageInstance.setViewport({ width: 1280, height: 720 });
  }
  return pageInstance;
}

export async function executeBrowserAction(args: Record<string, unknown>, toolCallId: string): Promise<ToolResult> {
  const { action, url, selector, value, extract_type = 'text', wait_for } = args as BrowserArgs;

  try {
    const page = await getPage();

    switch (action) {
      case 'navigate': {
        if (!url) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'URL is required for navigate action' }),
            success: false,
            error: 'URL is required',
            content: JSON.stringify({ error: 'URL is required' }),
          };
        }

        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        // Wait for optional selector
        if (wait_for) {
          await page.waitForSelector(wait_for, { timeout: 10000 }).catch(() => {});
        }

        const title = await page.title();
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ 
            success: true, 
            action: 'navigate',
            title,
            url: page.url(),
          }),
          success: true,
          content: JSON.stringify({ 
            success: true, 
            action: 'navigate',
            title,
            url: page.url(),
          }),
        };
      }

      case 'screenshot': {
        const screenshot = await page.screenshot({ 
          encoding: 'base64',
          fullPage: true,
        });
        
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ 
            success: true, 
            action: 'screenshot',
            screenshot: `data:image/png;base64,${screenshot}`,
          }),
          success: true,
          content: JSON.stringify({ 
            success: true, 
            action: 'screenshot',
            screenshot: `data:image/png;base64,${screenshot}`,
          }),
        };
      }

      case 'click': {
        if (!selector) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Selector is required for click action' }),
            success: false,
            error: 'Selector is required',
            content: JSON.stringify({ error: 'Selector is required' }),
          };
        }

        await page.waitForSelector(selector, { timeout: 10000 });
        await page.click(selector);
        
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, action: 'click', selector }),
          success: true,
          content: JSON.stringify({ success: true, action: 'click', selector }),
        };
      }

      case 'fill': {
        if (!selector || value === undefined) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Selector and value are required for fill action' }),
            success: false,
            error: 'Selector and value are required',
            content: JSON.stringify({ error: 'Selector and value are required' }),
          };
        }

        await page.waitForSelector(selector, { timeout: 10000 });
        await page.fill(selector, String(value));
        
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, action: 'fill', selector }),
          success: true,
          content: JSON.stringify({ success: true, action: 'fill', selector }),
        };
      }

      case 'extract': {
        if (!selector) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Selector is required for extract action' }),
            success: false,
            error: 'Selector is required',
            content: JSON.stringify({ error: 'Selector is required' }),
          };
        }

        await page.waitForSelector(selector, { timeout: 10000 });

        let extracted: string | Record<string, string> = '';
        
        if (extract_type === 'all') {
          const elements = await page.$$(selector);
          extracted = await Promise.all(
            elements.map(async (el) => {
              const text = await el.textContent();
              const href = await el.$eval('a', (a: any) => a.href).catch(() => null);
              const src = await el.$eval('img', (img: any) => img.src).catch(() => null);
              return { text: text?.trim(), href, src };
            })
          );
        } else if (extract_type === 'href') {
          extracted = await page.$eval(selector, (el: any) => el.href).catch(() => '');
        } else if (extract_type === 'src') {
          extracted = await page.$eval(selector, (el: any) => el.src).catch(() => '');
        } else {
          extracted = await page.$eval(selector, (el: any) => el.textContent).catch(() => '');
        }

        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, action: 'extract', extracted }),
          success: true,
          content: JSON.stringify({ success: true, action: 'extract', extracted }),
        };
      }

      case 'scroll': {
        const scrollAmount = (args as any).scroll_amount || 500;
        await page.evaluate((amount) => window.scrollBy(0, amount), scrollAmount);
        
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, action: 'scroll', scrollAmount }),
          success: true,
          content: JSON.stringify({ success: true, action: 'scroll', scrollAmount }),
        };
      }

      case 'get_html': {
        const html = await page.content();
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, action: 'get_html', html }),
          success: true,
          content: JSON.stringify({ success: true, action: 'get_html', html }),
        };
      }

      default:
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ error: `Unknown action: ${action}` }),
          success: false,
          error: `Unknown action: ${action}`,
          content: JSON.stringify({ error: `Unknown action: ${action}` }),
        };
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: errorMessage }),
      success: false,
      error: errorMessage,
      content: JSON.stringify({ error: errorMessage }),
    };
  }
}

// Cleanup function to close browser
export async function closeBrowser() {
  if (pageInstance) {
    await pageInstance.close();
    pageInstance = null;
  }
  if (browserInstance) {
    await browserInstance.close();
    browserInstance = null;
  }
}