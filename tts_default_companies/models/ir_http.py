from odoo import models
from odoo.http import request

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        
        # Check if we have a valid request context
        if not request or not request.session or not request.session.uid:
            return result
            
        user = self.env.user
        
        # Check if the user is an internal user (usually only they have multiple companies)
        if not user._is_internal():
            return result
            
        # The frontend uses the 'cids' cookie to determine active companies.
        # If it is not set (e.g. on first load after login), we inject our defaults.
        if not request.httprequest.cookies.get('cids'):
            if user.default_enabled_company_ids:
                # Ensure the default enabled companies are part of allowed companies to avoid security errors
                allowed_cids = user._get_company_ids()
                valid_cids = [c.id for c in user.default_enabled_company_ids if c.id in allowed_cids]
                
                if valid_cids:
                    # 'cids' cookie format is '1-2-3'
                    cids_str = '-'.join(str(cid) for cid in valid_cids)
                    
                    # Set the cookie on the response so the frontend JS picks it up
                    if hasattr(request, 'future_response'):
                        request.future_response.set_cookie('cids', cids_str)
                        
                    # We can also update 'current_company' in user_companies to match the first enabled one
                    # if we want to ensure consistency, though the cookie should be enough.
                    if 'user_companies' in result:
                        result['user_companies']['current_company'] = valid_cids[0]

        return result
