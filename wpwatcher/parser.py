#! /usr/bin/env python3
# 
# WPScan output parser
# 
# Authors: Florian Roth, Tristan Landès
#
# DISCLAIMER - USE AT YOUR OWN RISK.
#
# You can import this package into your application and call `parse_results` method.
#   from wpwatcher.parser import parse_results
#   (messages, warnings, alerts) = parse_results(wpscan_output_string)

# Parse know vulnerabilities
    # Parse vulnerability data and make more human readable.
    # NOTE: You need an API token for the WPVulnDB vulnerability data.

"""
All the WPScan fields for the JSON output in the views/json folders at:

https://github.com/wpscanteam/CMSScanner/tree/master/app/views/json
https://github.com/wpscanteam/wpscan/tree/master/app/views/json

Here are some other inspirational ressources found about parsing wpscan json

Generates a nice table output (Rust code) 
    https://github.com/lukaspustina/wpscan-analyze
    Parser code: 
        https://github.com/lukaspustina/wpscan-analyze/blob/master/src/analyze.rs
Python parser (do not parse for vulnerable theme or outdated warnings) 
    https://github.com/aaronweaver/AppSecPipeline/blob/master/tools/wpscan/parser.py
Vulcan wpscan (Go) 
    https://github.com/adevinta/vulcan-checks/blob/master/cmd/vulcan-wpscan/wpscan.go
    Great job listing all the fields, is the list complete ?
Dradis ruby json Parser 
    https://github.com/dradis/dradis-wpscan/blob/master/lib/dradis/plugins/wpscan/importer.rb : 
    No warnings neither but probably the clearest code

Ressource PArsing CLI output:
    List of all icons: https://github.com/wpscanteam/CMSScanner/blob/master/app/formatters/cli.rb
"""

import json
import re
from abc import ABC, abstractmethod

class Component(ABC):
    def __init__(self, data): 
        """Base abstract class for all WPScan JSON components"""
        if not data:
            data={}
        self.data=data

    @abstractmethod
    def get_infos(self):
        pass

    @abstractmethod
    def get_warnings(self):
        pass

    @abstractmethod
    def get_alerts(self):
        pass

    def __str__(self):
        return('\n\n'.join(self.get_alerts()+self.get_warnings+self.get_infos()))
    
    def __repr__(self):
        return(json.dumps(self.data, indent=4))

class WPScanJsonParser(Component):
    def __init__(self, data, false_positives_strings=None):
        """Main interface to parse WPScan JSON data"""
        Component.__init__(self, data)

        self.false_positives_strings=false_positives_strings if false_positives_strings else []
        self.components=[]
        # Add components to list
        # ... WIP

    def get_infos(self):
        """Add false positives as infos with "[False positive]" prefix"""
        infos=[]
        for component in self.components:
            infos.extend(component.get_infos())

            for alert in component.get_alerts()+component.get_warnings():
                if self.is_false_positive(alert, self.false_positives_strings):
                    infos.append("[False positive]\n"+alert)

        return infos

    def get_warnings(self):
        """Igore false positives and automatically remove special warning if all vuln are ignored"""
        warnings=[]
        for component in self.components:
            all_warnings=component.get_warnings()
            component_warnings=self.ignore_false_positives(all_warnings, self.false_positives_strings)
            # Automatically remove special warning if all vuln are ignored
            if len(component_warnings)==1 and 'The version could not be determined' in component_warnings[0]:
                component_warnings=[]

            warnings.extend(component_warnings)
            
        return warnings

    def get_alerts(self):
        """Igore false positives"""
        alerts=[]
        for component in self.components:
            alerts.extend(self.ignore_false_positives(component.get_alerts(), self.false_positives_strings))
        return alerts

    @staticmethod
    def ignore_false_positives(messages, false_positives_strings):
        """Process false positives"""
        for alert in messages:
            if WPScanJsonParser.is_false_positive(alert, false_positives_strings):
                messages.remove(alert)
        return messages

    @staticmethod
    def is_false_positive(string, false_positives_strings):
        """False Positive Detection"""
        for fp_string in false_positives_strings:
            if fp_string in string:
                return True

class Vulnerability(Component):
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/finding.erb"""
        super().__init__(self, data)

        self.title=data.get('title', None)
        self.cvss=data.get('cvss', None)
        self.fixed_in=data.get('fixed_in', None)
        self.references=data.get('references', None)

    def get_alerts(self):
        """Return 1 alert. First line of alert string is the vulnerability title. Process CVE and WPVulnDB references to add links"""
        alert=self.title

        if self.cvss: 
            alert+='\nCVSS: {}'.format(self.cvss)
        if self.fixed_in: 
            alert+='\nFixed in: {}'.format(self.fixed_in)
        else:
            alert+='\nNot fixed yet'
        if self.references: 
            alert+='\nReferences: '
            for ref in self.references:
                if ref == 'cve':
                    for cve in self.references[ref]: 
                        alert+="\n- CVE: http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-{}".format(cve)
                elif ref == 'wpvulndb': 
                    for wpvulndb in self.references[ref]:
                        alert+="\n- WPVulnDB: https://wpvulndb.com/vulnerabilities/{}".format(wpvulndb)
                else:
                    for link in self.references[ref]:
                        alert+="\n- {ref}: {link}".format(ref=ref.title(), link=link)

        return([alert])

    def get_warnings(self):
        """Return empty list"""
        return []

    def get_infos(self):
        """Return empty list"""
        return []

class Finding(Component):
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/finding.erb"""
        super().__init__(self, data)

        self.found_by=data.get("found_by", None)
        self.confidence=data.get("confidence", None)
        self.interesting_entries=data.get("interesting_entries", None)
        self.confirmed_by=data.get("confirmed_by", None)
        self.vulnerabilities=[Vulnerability(vuln) for vuln in data.get("vulnerabilities", [])]

    def get_alerts(self):
        """Return list of vulnerabilities"""
        alerts=[]
        for v in self.vulnerabilities:
            alerts.extend(v.get_alerts())
        return alerts

    def get_infos(self):
        """Return 1 info"""
        info=""
        if self.found_by:
            info+="Found by: {}".format(self.found_by)
        if self.confidence: 
            info+="(confidence: {})".format(self.confidence)
        if self.interesting_entries: 
            info+="\nInteresting entries: \n- {}".format('\n- '.join(self.interesting_entries))
        if self.confirmed_by: 
            info+="Confirmed by: "
            for entry in self.confirmed_by:
                info+="\n- {} (confidence: {})".format(entry)
                if self.confirmed_by[entry].get('confidence', None): 
                    info+="(confidence: {})".format(self.confirmed_by[entry]['confidence'])
                if self.confirmed_by.get("interesting_entries", None):
                    info+="\n  Interesting entries: \n  - {}".format('\n  - '.join(self.confirmed_by.get("interesting_entries")))
        return [info]

class WPItemVersion(Finding):
    
    def __init__(self, data): 
        """ Themes, plugins and timthumbs Version. From:
        https://github.com/wpscanteam/wpscan/blob/master/app/views/json/theme.erb
        https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/plugins.erb
        https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/timthumbs.erb
        """
        super().__init__(self, data)
        self.number=data.get('number', data)
    
    def get_alerts(self):
        """Return any item version vulnerabilities"""
        return super().get_alerts()

    def get_warnings(self):
        """Return empty list"""
        return []

    def get_infos(self):
        """Return 1 info"""
        info="Version: {} ".format(self.number)
        info+="\n{}".format(super().get_infos()[0])
        return [info]

class WPItem(Finding):
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/wp_item.erb"""
        super().__init__(self, data)

        self.slug=data.get('slug', None)
        self.location=data.get('location', None)
        self.latest_version=data.get('latest_version', None)
        self.last_updated=data.get('last_updated', None)
        self.outdated=data.get('outdated', None)
        self.readme_url=data.get('readme_url', None)
        self.directory_listing=data.get('directory_listing', None)
        self.error_log_url=data.get('error_log_url', None) 
        self.version=WPItemVersion(data.get('version', None))

    def _get_warnings(self):
        """Return 0 or 1 warning. The warning can contain infos about oudated plugin, directory listing or accessible error log.
        First line of warning string is the plugin slug. Location also added as a reference."""
        warning=self.slug

        # Test if there is issues
        issue_data=""
        if self.outdated: 
            issue_data+="\nThe version is out of date, the latest version is {}".format(self.latest_version)
        if self.directory_listing: 
            issue_data+="\nDirectory listing is enabled"
        if self.error_log_url: 
            issue_data+="\nAn error log file has been found: {}".format(self.error_log_url)

        if not issue_data: 
            return [] # Return if no issues

        else: 
            warning+=issue_data

        if self.location: 
            warning += "\nLocation: {}".format(self.location)

        return([warning])

    def get_alerts(self):
        """Return list of know plugin or theme vulnerability. Empty list is returned if plugin version is unrecognized"""
        alerts=[]
        if self.version:
            alerts.extend(super().get_alerts())
            alerts.extend(self.version.get_alerts())
        return alerts

    def get_warnings(self):
        """Return plugin or theme warnings, if oudated plugin, directory listing, accessible error log and 
        for all know vulnerabilities if plugin version could not be recognized.
        Adds a special warning saying the version is unrecognized if that's the case"""
        warnings=[]
        # Get oudated theme warning
        warnings.extend(self._get_warnings())
        # If vulns are found and the version is unrecognized
        if not self.version and super().get_alerts():
            # Adds a special warning saying the version is unrecognized
            warnings.append("""{}\nThe plugin or theme version could not be determined by WPScan, all known vulnerabilities are listed. 
            Add vulnerabilities titles to false positves strings to ignore these messages.""".format(self.slug))
            warnings.extend(super().get_alerts())
        return warnings

    def get_infos(self):
        """Return 1 info"""
        info=self.slug
        if self.location: 
            info += "\nLocation: {}".format(self.location)
        if self.latest_version:
            info += "\nLatest Version: {} {}".format(self.latest_version, '(up to date)' if not self.outdated else '')
        if self.last_updated:
            info += "\nLast Updated: {}".format(self.last_updated)
        if self.readme_url:
            info += "\nReadme: {}".format(self.readme_url)
        if self.version:
            info += "\n{}".format(self.version.get_infos()[0])
        else:
            info += "\nThe version could not be determined"
        info+=super().get_infos()[0]
        return [info]

class Plugin(WPItem):
    def __init__(self, data):
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/plugins.erb"""
        super().__init__(self, data)

    def get_infos(self):
        """Return 1 info"""
        return ["Plugin: {}".format(super().get_infos()[0])]

    def get_warnings(self):
        """Return plugin warnings"""
        if super().get_warnings():
            return [ "Plugin Warning: {}".format (super().get_warnings()[i]) 
                for i in range(len(super().get_warnings())) ]

    def get_alerts(self):
        """Return plugin vulnerabilities"""
        if super().get_alerts():
            return [ "Plugin Vulnerability: {}".format (super().get_alerts()[i]) 
                for i in range(len(super().get_alerts())) ]

class Theme(WPItem):
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/theme.erb"""
        super().__init__(self, data)

        self.style_url=data.get('style_url', None)
        self.style_name=data.get('style_name', None)
        self.style_uri=data.get('style_uri', None)
        self.description=data.get('description', None)
        self.author=data.get('author', None)
        self.author_uri=data.get('author_uri', None)
        self.template=data.get('template', None)
        self.license=data.get('license', None)
        self.license_uri=data.get('license_uri', None)
        self.tags=data.get('tags', None)
        self.text_domain=data.get('text_domain', None)
        self.parents=[Theme(theme) for theme in data.get('parents', [])]

    def get_infos(self):
        """Return 1 info"""
        info=super().get_infos()[0]

        if self.style_url:
            info+="\nStyle URL: {}".format(self.style_url)
        if self.style_name:
            info+="\nStyle Name: {}".format(self.style_name)
        if self.style_uri:
            info+="\nStyle URI:: {}".format(self.style_uri)
        if self.description:
            info+="\nDescription: {}".format(self.description)
        if self.author:
            info+="\nAuthor: {}".format(self.author)
        if self.author_uri:
            info+="\nAuthor URI: {}".format(self.author_uri)
        if self.template:
            info+="\nTemplate: {}".format(self.template)
        if self.license:
            info+="\nLicense: {}".format(self.license)
        if self.license_uri:
            info+="\nLicense URI: {}".format(self.license_uri)
        if self.tags:
            info+="\nTags: {}".format(self.tags)
        if self.text_domain:
            info+="\nDomain {}".format(self.text_domain)

        info+="\n{}".format(Finding.get_infos(self)[0])
        if self.parents:
            info+="\nParent Theme(s): {}".format(', '.join([p.slug for p in self.parents]))
        
        info = "Theme: {}".format(info)
        return [info]

    def get_warnings(self):
        """Return theme warnings"""
        if super().get_warnings():
            return [ "Theme Warning: {}".format (super().get_warnings()[i]) 
                for i in range(len(super().get_warnings())) ]

    def get_alerts(self):
        """Return theme vulnerabilities"""
        if super().get_alerts():
            return [ "Theme Vulnerability: {}".format (super().get_alerts()[i]) 
                for i in range(len(super().get_alerts())) ]

class Timthumb(Finding):
    
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/timthumbs.erb"""
        super().__init__(self, data)
        self.url=None
        self.version=WPItemVersion(data.get('version', None))

    def get_infos(self):
        """Return 1 info"""
        info="Timthumb: {}\n{}".format(self.url, super().get_infos()[0])
        if self.version:
                info += "\n{}".format(self.version.get_infos()[0])
        else:
            info += "\nThe version could not be determined"
        return [info]

    def get_warnings(self):
        """Return empty list"""
        return []

    def get_alerts(self):
        """Return timthumb vulnerabilities"""
        if super().get_alerts():
            return [ "Timthumb Vulnerability: {}".format(alert) for alert in super().get_alerts()+ self.version.get_alerts() ]


class MainTheme(Theme): 
    
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/main_theme/theme.erb"""
        super().__init__(self, data)

    def get_infos(self):
        """Return 1 info"""
        return ["Main Theme: {}".format(super().get_infos()[0])]

    def get_warnings(self):
        """Return Main Theme warnings"""
        if super().get_warnings():
            return [ "Main Theme Warning: {}".format(warning) for warning in super().get_warnings() ]

    def get_alerts(self):
        """Return Main Theme vulnerabilities"""
        if super().get_alerts():
            return [ "Main Theme Vulnerability: {}".format(alert) for alert in super().get_alerts() ]

class WPVersion(Finding):
    
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/wp_version/version.erb"""
        super().__init__(self, data)
        self.number=data.get('number', None)
        self.release_date=data.get('release_date', None)
        self.status=data.get('status', None)

    def get_infos(self):
        """Return 1 info"""
        if self.number:
            info="Wordpress Version: {}".format(self.number)
            if self.release_date:
                info+="Release Date: {}".format(self.release_date)
            if self.status:
                info+="Status: {}".format(self.status.title())  
        else:
            info="Wordpress Version: The WordPress version could not be detected"
       
        if super().get_infos()[0]:
            info+="\n{}".format(super().get_infos()[0])

        return [info]

    def get_warnings(self):
        """Return 0 or 1 Wordpress Version Warning"""
       
        if self.status=="insecure":
            warning="Wordpress Version Warning: "
            warning+="Insecure WordPress version {} identified (released on {})".format(self.number, self.release_date)
            return [warning]
        else:
            return []

    def get_alerts(self):
        """Return Wordpress Version vulnerabilities"""
        if super().get_alerts():
            return [ "Wordpress Version Vulnerability: {}".format(alert) for alert in super().get_alerts() ]

class DBExport(Finding):
    
    def __init__(self, url, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/db_exports.erb"""
        super().__init__(self, data)
        self.url=url

    def get_alerts(self):
        """Return DBExport alerts"""
        alert="Database Export: {}\n{}".format(self.url, super().get_infos()[0])
        return [alert]
    
    def get_warnings(self):
        """Return empty list"""
        return []

    def get_infos(self):
        """Return empty list"""
        return []

class User(Finding):
    
    def __init__(self, username, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/users.erb
        And https://github.com/wpscanteam/wpscan/blob/master/app/views/json/password_attack/users.erb
        """
        super().__init__(self, data)
        
        self.username=username
        self.id=data.get('id', None)
        self.password=data.get('password', None)

    def get_infos(self):
        """Return 1 info"""
        info="User Identified: {}".format(self.username)
        info+="\n{}".format(super().get_infos())
        return [info]

    def get_warnings(self):
        """Return empty list"""
        return []

    def get_alerts(self):
        """Return 1 alert if username / password are found""""
        if self.password:
            alert="Username: {}".format(self.username)
            alert+="Password: {}".format(self.password)
            return [alert]
        else:
            return []

class PasswordAttack(Component):
    
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/password_attack/users.erb"""
        super().__init__(self, data)

        self.users = [ User(user, data.get(user)) for user in data ] 

        def get_alerts(self):
            """Return Password Attack Valid Combinations Found alerts"""
            alerts=[]
            for user in self.users:
                alert="Password Attack Valid Combinations Found:"
                if user.get_alerts():
                    alert+="\n{}".format(user.get_alerts()[0])
                    alerts.append(alert)

            return alerts
    
        def get_warnings(self):
            """Return empty list"""
            return []

        def get_infos(self):
            """Return empty list"""
            return []

class NotFullyConfigured(Component):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/core/not_fully_configured.erb"""
        super().__init__(self, data)
        self.not_fully_configured=data.get('not_fully_configured', None)
    
    def get_alerts(self):
        """Return 0 or 1 alert"""
        if self.not_fully_configured: 
            return ["Wordpress Alert: {}".format(self.not_fully_configured)]
        else:
            return []

    def get_warnings(self):
        """Return empty list"""
        return []

    def get_infos(self):
        """Return empty list"""
        return []


# WIP ...

class Media(Finding):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/medias.erb"""
        super().__init__(self, data)
        self.url=None

class ConfigBackup(Finding):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/enumeration/config_backups.erb"""
        super().__init__(self, data)
        self.url=None

class VulnAPI(Component):
    
    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/vuln_api/status.erb"""
        super().__init__(self, data)

        self.http_error=None
        self.plan=None
        self.requests_done_during_scan=None
        self.requests_remaining=None
        self.error=None

class InterestingFinding(Finding):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/CMSScanner/blob/master/app/views/json/interesting_findings/findings.erb"""
        super().__init__(self, data)
        self.url=None
        self.to_s=None
        self.type=None
        self.references=None

class Banner(Component):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/wpscan/blob/master/app/views/json/core/banner.erb"""
        super().__init__(self, data)

        self.description=None

class ScanStarted(Component):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/CMSScanner/blob/master/app/views/json/core/started.erb"""
        super().__init__(self, data)

        self.start_time=None
        self.start_memory=None
        self.target_url=None
        self.target_ip=None
        self.effective_url=None

class ScanFinished(Component):

    def __init__(self, data): 
        """From https://github.com/wpscanteam/CMSScanner/blob/master/app/views/json/core/finished.erb"""
        super().__init__(self, data)

        self.stop_time=None
        self.elapsed=None
        self.requests_done=None
        self.cached_requests=None
        self.data_sent_humanised=None
        self.data_received_humanised=None
        self.used_memory_humanised=None

def parse_results(wpscan_output, false_positives=[]):
    # Init scan messages
    ( messages, warnings, alerts ) = ([],[],[])
    is_json=False
    try:
        data=json.loads(wpscan_output)
        is_json=True
    except ValueError: pass
    if is_json: (messages, warnings, alerts)=parse_json(data)
    else:  (messages, warnings, alerts)=parse_cli(wpscan_output, false_positives)
    return (ignore_false_positives( messages, warnings, alerts, false_positives))   

def parse_cli_toogle(line, warning_on, alert_on):
    # Color parsing
    if "33m[!]" in line: warning_on=True
    elif "31m[!]" in line: alert_on = True
    # No color parsing Warnings string are hard coded here
    elif "[!]" in line and any([m in line for m in [   
        "The version is out of date",
        "No WPVulnDB API Token given",
        "You can get a free API token"]]) :
        warning_on = True
    elif "[!]" in line :
        alert_on = True
    # Both method with color and no color apply supplementary proccessing 
    # Warning for insecure Wordpress
    if 'Insecure' in line: 
        warning_on = True
    # Lower voice of Vulnerabilities found but not plugin version
    if 'The version could not be determined' in line and alert_on:
        alert_on = False  
        warning_on = True 
    return ((warning_on, alert_on))

def parse_cli(wpscan_output, false_positives):
    if "[+]" not in wpscan_output: 
        raise ValueError("The file does not seem to be a WPScan CLI log.")
    # Init scan messages
    ( messages, warnings, alerts ) = ([],[],[])
    # Init messages toogles
    warning_on, alert_on = False, False
    message_lines=[] 
    current_message=""

    # Every blank ("") line will be considered as a message separator
    for line in wpscan_output.splitlines()+[""]:

        # Parse all output lines and build infos, warnings and alerts
        line=line.strip()
        
        # Parse line
        warning_on, alert_on = parse_cli_toogle(line, warning_on, alert_on)

        # Remove colorization anyway after parsing
        line = re.sub(r'(\x1b|\[[0-9][0-9]?m)','',line)
        # Append line to message. Handle the begin of the message case
        message_lines.append(line)

        # Build message
        current_message='\n'.join([m for m in message_lines if m not in ["","|"]]).strip()

        # Message separator just a white line.
        # Only if the message if not empty. 
        if ( line.strip() not in [""] or current_message.strip() == "" ) : 
            continue

        # End of the message

        # Post process message to separate ALERTS into different messages of same status and add rest of the infos to warnings
        if (alert_on or warning_on) and any(s in current_message for s in ['vulnerabilities identified','vulnerability identified']) : 
            messages_separated=[]
            msg=[]
            for l in message_lines+["|"]:
                if l.strip() == "|":
                    messages_separated.append('\n'.join([ m for m in msg if m not in ["","|"]] ))
                    msg=[]
                msg.append(l)

            # Append Vulnerabilities messages to ALERTS and other infos in one message
            vulnerabilities = [ m for m in messages_separated if '| [!] Title' in m.splitlines()[0] ]
            if alert_on: alerts.extend(vulnerabilities)
            elif warning_on: warnings.extend(vulnerabilities)

            # Add rest of the plugin infos to warnings or infos if every vulnerabilities are ignore
            plugin_infos='\n'.join([ m for m in messages_separated if '| [!] Title' not in m.splitlines()[0] ])
            
            if len([v for v in vulnerabilities if not is_false_positive(v, false_positives)])>0:
                warnings.append(plugin_infos)
            else:
                messages.append("[False positive]\n"+plugin_infos)

        elif warning_on: warnings.append(current_message)
        else: messages.append(current_message)
        message_lines=[]
        current_message=""
        # Reset Toogle Warning/Alert
        warning_on, alert_on = False, False

    return (( messages, warnings, alerts ))

######### JSON PARSING FROM HERE #########

def parse_json(data):
    infos, warnings, alerts=[],[],[]
    # Do a sanity check to confirm the data is ok
    if not data or not 'target_url' in data or not data['target_url']:
        raise ValueError("No data in wpscan JSON output (None) or no 'target_url' field present in the provided Json data. The scan might have failed, data: \n"+str(data))

    # warnings, alerts=parse_vulnerabilities_and_outdated(data)
    # infos.extend(parse_misc_infos(data))
    # warnings.extend(parse_misc_warnings(data))
    # alerts.extend(parse_misc_alerts(data))
    wp_warning = parse_warning_wordpress(data.get('version', None))
    if wp_warning: 
        warnings.append(wp_warning)

    main_theme_warning = parse_warning_theme_or_plugin(data.get('main_theme', None))
    if main_theme_warning: 
        warnings.append(main_theme_warning)

    for slug in data.get('plugins', {}):
        plugin_warning = parse_warning_theme_or_plugin(data.get('plugins').get(slug))
        if plugin_warning: 
            if not data.get('plugins').get(slug).get('version', None):
                plugin_warning+="\nThe version could not be determined, all known vulnerabilites are listed"
            warnings.append(plugin_warning)
    # WIP

    return (( infos, warnings, alerts ))

def parse_warning_wordpress(finding):
    if not finding: 
        return None
    if finding.get('status', None)=="insecure":
        fdata=""
        fdata+="Insecure WordPress version %s identified (released on %s)"%(finding['number'], finding['release_date'])
        fdata+=parse_confidence(finding)
    return fdata
    
    # if "interesting_entries" in finding:
    #         if len(finding["interesting_entries"]) > 0:
    #             findingData += "\nInteresting Entries: %s" % (", ".join(finding["interesting_entries"]))
    # if "found_by" in finding:
    #         findingData += "\nFound by: %s" % finding["found_by"]

def parse_warning_theme_or_plugin(finding):
    if not finding: 
        return None
    fdata=""
    if 'slug' in finding:
        fdata+="%s" % finding['slug']
    # Test if there is issues
    issue_data=""
    if finding.get('outdated', None): 
        issue_data+="\nThe version is out of date, the latest version is %s" % (finding["latest_version"])
    if finding.get('directory_listing', None): 
        issue_data+="\nDirectory listing is enabled"
    if finding.get('error_log_url', None): 
        issue_data+="\nAn error log file has been found: %s" % (finding["error_log_url"])

    if not issue_data: 
        return None # Return if no issues
    else: 
        fdata+=issue_data

    if "location" in finding: 
        fdata += "\nLocation: %s" % finding["location"]

    # if "found_by" in finding:
    #     fdata += "\nFound by: %s" % finding["found_by"]

    fdata+=parse_confidence(finding)
    # fdata+=parse_interesting_entries(finding)
    return(fdata)



def parse_vulnerability(finding):
    # Finding can be a vulnerability or other
    findingData = ""
    refData = ""
    title=""
    # title = "%s:"%(finding_type) if finding_type else ""

    # if type(finding) is not dict: 
    #     raise TypeError("Must be a dict, method parse_a_finding() for data {}".format(finding)) 

    # For interesting findings
    # if "type" in finding: title += "%s\n" % finding["type"]
    # if "to_s" in finding: title += "%s" % finding["to_s"]
    # For vulnerabilities
    if "title" in finding: title += "%s" % finding["title"]
    findingData += "%s" % title
    if "fixed_in" in finding: findingData += "\nFixed In: %s" % finding["fixed_in"]
    # if "url" in finding: findingData += "\nURL: %s" % finding["url"]
    # findingData+=parse_confidence(finding)
    # findingData+=parse_interesting_entries(finding)
    refData=parse_references(finding)

    # if "comfirmed_by" in finding:
    #     if len(finding["confirmed_by"]) > 0:
    #         findingData += "\nConfirmed By:\n"
    #         findingData+="\n- ".join(finding["confirmed_by"])
    # if "found_by" in finding:
    #     findingData += "\nFound by: %s" % finding["found_by"]

    return ("%s %s" % (findingData, refData) )

######## END RE WRITE ########


def check_valid_section(data, section):
    if section in data and ( data[section] is not None or len(data[section])>0 ) : return True
    else: return False

def parse_slugs_vulnerabilities(node):
    warnings, alerts=[],[]
    if not node: return ((warnings, alerts))
    for slug in node:
        try: alerts.extend(parse_findings(node[slug]['vulnerabilities']))
        except KeyError: pass
        try: warnings.extend(parse_warning_theme_or_plugin(node[slug]))
        except KeyError: pass
    return ((warnings, alerts))

def parse_section_alerts(section, node):
    warnings, alerts=[],[]
    if not node: return ((warnings, alerts))
    if section=='version':
        warnings.extend(parse_warning_wordpress(node))
    if section=='main_theme':
        warnings.extend(parse_warning_theme_or_plugin(node))
    if any ([section==c for c in ['main_theme','version']]):
        try: alerts.extend(parse_findings(node['vulnerabilities']))
        except KeyError: pass
    warnings_alt,alerts_alt=[],[]
    if any([section==c for c in ['themes', 'plugins', 'timthumbs']]):
        warnings_alt, alerts_alt=parse_slugs_vulnerabilities(node)
        warnings.extend(warnings_alt)
        alerts.extend(alerts_alt)
    return ((warnings, alerts))

def parse_vulnerabilities_and_outdated(data):
    warnings, alerts=[],[]
    for section in data:
        warnings_sec, alerts_sec = parse_section_alerts(section, data[section])
        alerts.extend(alerts_sec)
        warnings.extend(warnings_sec)
    return ((warnings, alerts))

def wrap_parse_finding(data, section):
    alerts=[]
    if check_valid_section(data, section) :
        alerts.extend(parse_vulnerability_or_finding(data[section]))
    return alerts

def wrap_parse_simple_values(data, section, title):
    alerts=[]
    if check_valid_section(data, section) :
        for val in data[section]:
            alerts.append("%s%s"%(title, str(val)))
    return alerts

def parse_misc_alerts(data):
    return ( wrap_parse_simple_values(data, 'config_backups', 'WordPress Configuration Backup Found: ') + 
        wrap_parse_finding(data, 'db_exports')+ 
        wrap_parse_simple_values(data, 'password_attack', 'WordPres Weak User Password Found: ')+
        wrap_parse_finding(data, 'not_fully_configured') )

def parse_misc_warnings(data):
    warnings=wrap_parse_finding(data, 'medias')
    if check_valid_section(data, 'vuln_api') and 'error' in data['vuln_api']:
            warnings.append(data['vuln_api']['error'])
    return warnings

def parse_banner(data):
    if not check_valid_section(data, 'banner') : return []
    return wrap_parse_simple_values(data['banner'], 'version', 'Scanned with WPScan version: ')

def parse_target(data):
    messages=[]
    messages.append("Target URL: {}\nIP: {}\nEffective URL: {}".format(
        data['target_url'],
        data["target_ip"] if 'target_ip' in data else '?',
        data["effective_url"]))
    return messages

def parse_misc_infos(data):
    messages=parse_target(data)
    messages.extend(parse_banner(data))
    if check_valid_section(data, 'interesting_findings') :
        # Parse informations
        messages.extend(parse_findings(data["interesting_findings"]) )
    messages.extend(wrap_parse_simple_values(data, 'users', 'WordPress user found: '))
    return (messages)

def parse_interesting_entries(finding):
    fdata=""
    if check_valid_section(finding, 'interesting_entries') :
        fdata += "\nInteresting Entries: %s" % (", ".join(finding["interesting_entries"]))
    return fdata

def parse_confidence(finding):
    fdata=""
    if "confidence" in finding:
            fdata += "\nConfidence: %s" % finding["confidence"]
    return fdata

# Wrapper to parse findings can take list or dict type
def parse_findings(findings):
    summary = []
    if type(findings) is list:
        for finding in findings:
            summary.append(parse_vulnerability_or_finding(finding))
    elif type(findings) is dict:
        for finding in findings:
            summary.append(parse_vulnerability_or_finding(findings[finding]))
    else: raise TypeError("Must be a list or dict, method parse_findings() for data: {}".format(findings)) 
    return(summary)

# def parse_version_info(version):
#     headerInfo = ""

#     if "number" in version:
#         headerInfo += "Running WordPress version: %s\n" % version["number"]

#     if "interesting_entries" in version:
#             if len(version["interesting_entries"]) > 0:
#                 headerInfo += "\nInteresting Entries: %s" % (", ".join(version["interesting_entries"]))

#     return headerInfo