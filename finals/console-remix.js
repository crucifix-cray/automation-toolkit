// ==================================================
// LOVABLE HIGH CREDIT AUTOMATION - CONSOLE SCRIPT
// Run this in browser console at /templates page
// ==================================================

(async function() {
    console.log("🚀 Starting high credit automation from /templates...");
    
    // Helper: Human delay
    const humanDelay = (min = 500, max = 1500) => {
        return new Promise(resolve => setTimeout(resolve, Math.random() * (max - min) + min));
    };
    
    // Helper: Human type
    const humanType = async (element, text) => {
        element.focus();
        await humanDelay(200, 400);
        
        for (let char of text) {
            element.value += char;
            element.dispatchEvent(new Event('input', { bubbles: true }));
            await humanDelay(80, 200);
            
            // Random pause
            if (Math.random() < 0.15) {
                await humanDelay(300, 700);
            }
        }
    };
    
    // Helper: Human click
    const humanClick = async (element) => {
        // Scroll into view
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        await humanDelay(500, 1000);
        
        // Move mouse (simulate)
        const rect = element.getBoundingClientRect();
        console.log(`Moving to (${rect.x}, ${rect.y})`);
        await humanDelay(300, 600);
        
        // Click
        element.click();
        await humanDelay(200, 400);
    };
    
    try {
        // Step 1: Scroll page randomly
        console.log("📜 Scrolling page...");
        window.scrollBy(0, Math.random() * 500 + 100);
        await humanDelay(1000, 2000);
        window.scrollBy(0, Math.random() * 500 + 100);
        await humanDelay(1500, 3000);
        
        // Step 2: Get all template cards
        const cards = document.querySelectorAll('section[aria-label="All templates"] article');
        console.log(`Found ${cards.length} templates`);
        
        if (cards.length === 0) {
            console.error("❌ No template cards found!");
            return;
        }
        
        // Step 3: Pick random template
        const randomIdx = Math.floor(Math.random() * cards.length);
        const card = cards[randomIdx];
        console.log(`Selected template #${randomIdx}`);
        
        // Scroll card into view
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        await humanDelay(800, 1500);
        
        // Step 4: Hover over card
        card.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
        await humanDelay(800, 1500);
        
        // Step 5: Click 3-dot menu button
        const menuBtn = card.querySelector('button[aria-label*="More options"]');
        if (!menuBtn) {
            console.error("❌ Menu button not found!");
            return;
        }
        
        console.log("Clicking 3-dot menu...");
        await humanClick(menuBtn);
        await humanDelay(1000, 2000);
        
        // Step 6: Click "Remix" in dropdown
        await humanDelay(500, 1000);
        const remixMenuItem = document.querySelector('div[role="menuitem"]:has-text("Remix")');
        if (!remixMenuItem) {
            // Try alternative selector
            const menuItems = Array.from(document.querySelectorAll('div[role="menuitem"]'));
            const remixItem = menuItems.find(item => item.textContent.includes('Remix'));
            
            if (!remixItem) {
                console.error("❌ Remix menu item not found!");
                return;
            }
            
            console.log("Clicking Remix...");
            await humanClick(remixItem);
        } else {
            console.log("Clicking Remix...");
            await humanClick(remixMenuItem);
        }
        
        // Step 7: Wait for dialog
        await humanDelay(2000, 3000);
        console.log("📝 Handling remix dialog like a human...");
        
        // Step 8: Retype project title
        const titleInput = document.querySelector('input[id="project-title"]');
        if (titleInput) {
            const currentTitle = titleInput.value;
            console.log(`Current title: ${currentTitle}`);
            
            await humanClick(titleInput);
            await humanDelay(300, 600);
            
            // Select all and delete
            titleInput.select();
            await humanDelay(200, 400);
            titleInput.value = '';
            titleInput.dispatchEvent(new Event('input', { bubbles: true }));
            await humanDelay(400, 800);
            
            // Type it back
            console.log("Retyping title...");
            await humanType(titleInput, currentTitle);
            console.log("✅ Retyped title");
            await humanDelay(800, 1500);
        }
        
        // Step 9: Check for workspace warning
        const warning = document.querySelector('p:has-text("You are not allowed to create projects")');
        if (warning && warning.textContent.includes("not allowed")) {
            console.log("⚠️  Changing workspace...");
            
            const workspaceDropdown = document.querySelector('button[id="remix-target-workspace"]');
            if (workspaceDropdown) {
                await humanClick(workspaceDropdown);
                await humanDelay(1000, 1500);
                
                const options = document.querySelectorAll('div[role="option"]');
                if (options.length > 1) {
                    await humanClick(options[1]);
                    console.log("✅ Changed workspace");
                    await humanDelay(500, 1000);
                }
            }
        }
        
        // Step 10: Check security acknowledgement checkbox
        const checkbox = document.querySelector('button[id="security-acknowledgement"]');
        if (checkbox) {
            console.log("Checking security checkbox...");
            
            // Scroll into view
            checkbox.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await humanDelay(500, 1000);
            
            // Move mouse around randomly
            await humanDelay(300, 600);
            
            // Click checkbox
            await humanClick(checkbox);
            console.log("✅ Checked security acknowledgement");
            await humanDelay(800, 1500);
        } else {
            console.log("⚠️  No checkbox found");
        }
        
        // Step 11: Click "Acknowledge and remix" button
        const acknowledgeBtn = document.querySelector('button[type="submit"]');
        const acknowledgeText = Array.from(document.querySelectorAll('button[type="submit"]'))
            .find(btn => btn.textContent.includes("Acknowledge and remix"));
        
        const submitBtn = acknowledgeText || acknowledgeBtn;
        
        if (submitBtn) {
            console.log("Clicking Acknowledge and remix...");
            
            // Scroll into view
            submitBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await humanDelay(500, 1000);
            
            // Hover near button
            await humanDelay(400, 800);
            
            // Click it
            await humanClick(submitBtn);
            console.log("✅ Clicked Acknowledge and remix");
        } else {
            console.error("❌ Submit button not found!");
            return;
        }
        
        // Step 12: Wait for redirect
        console.log("⏳ Waiting for project to load...");
        await humanDelay(3000, 4000);
        
        // Check for error toast
        const errorToast = document.querySelector('li[data-sonner-toast][data-type="error"]');
        if (errorToast && errorToast.textContent.includes("suspicious activity")) {
            console.error("❌ REMIX BLOCKED - SUSPICIOUS ACTIVITY!");
            console.error(errorToast.textContent);
            return;
        }
        
        console.log("✅ AUTOMATION COMPLETE!");
        console.log("🎉 Check if you got redirected to the project page");
        
    } catch (error) {
        console.error("❌ Error:", error);
    }
})();
