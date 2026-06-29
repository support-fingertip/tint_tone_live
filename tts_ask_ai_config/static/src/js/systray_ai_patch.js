/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

const systrayRegistry = registry.category("systray");

if (systrayRegistry.contains("ai.systray_action")) {
    const aiItem = systrayRegistry.get("ai.systray_action");
    const originalIsDisplayed = aiItem.isDisplayed;

    aiItem.isDisplayed = (env) => {
        if (session.disable_ask_ai_systray) {
            return false;
        }
        return originalIsDisplayed ? originalIsDisplayed(env) : true;
    };
}
