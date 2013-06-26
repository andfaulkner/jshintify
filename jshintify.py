# -*- coding: utf-8 -*-
'''
Sublime text plugin that opens terminal.
'''

import sublime_plugin
import threading
import os
import sublime
import subprocess
import json

if os.name == "nt":
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
else:
    STARTUPINFO = None

SETTINGS = sublime.load_settings('Jshintify.sublime-settings')

RUN_ON_LOAD = SETTINGS.get('run_on_load', False)
RUN_ON_SAVE = SETTINGS.get('run_on_save', False)

ERRORS_SHOW_COUNT = SETTINGS.get('error_messages_show_count', False)
ERRORS_SHOW_FIRST = SETTINGS.get('error_messages_show_first', False)

EXTENSIONS = SETTINGS.get('extensions', [])

SHOW_DOT = SETTINGS.get('show_dot', False)
SHOW_OUTLINE = SETTINGS.get('show_outline', False)

# for now let's cache those errors
ERRORS = {}

class Jshintify(sublime_plugin.TextCommand):#pylint: disable-msg=R0903,W0232
    '''
    Run jshint from sublime with configured shortcut
    '''

    def run(self, edit):#pylint: disable-msg=R0903,W0232,W0613
        '''
        Sublime text runs this

        @param edit: sublime.Edit
        '''
        thread = JshintifyThread(self.view, ERRORS, SETTINGS)
        thread.start()
        progress_tracker(thread)

class JslintifyEventListener(sublime_plugin.EventListener):#pylint: disable-msg=R0903,W0232,W0613
    """
    Class for event listeners
    """

    def on_post_save(self, view):#pylint: disable-msg=R0201
        """
        Event triggered after file save
        """
        if RUN_ON_SAVE:
            thread = JshintifyThread(view, ERRORS, SETTINGS)
            thread.start()
            progress_tracker(thread)

    def on_load(self, view):#pylint: disable-msg=R0201
        """
        Event triggered after file open
        """
        if RUN_ON_LOAD:
            thread = JshintifyThread(view, ERRORS, SETTINGS)
            thread.start()
            progress_tracker(thread)

    def on_selection_modified(self, view):#pylint: disable-msg=R0201
        """ Event triggered during moving in editor """

        row = view.rowcol(view.sel()[0].begin())[0]

        if str(row + 1) in ERRORS:
            this_error = ERRORS[str(row + 1)][0]

            string = ''
            if ERRORS_SHOW_COUNT:
                string += "ERRORS : {count} | ".format(count = len(ERRORS[str(row + 1)]))

            if ERRORS_SHOW_FIRST:
                string += get_error_string(this_error)

            view.set_status("JSHint", string)

        elif view.get_status("JSHint"):
            view.erase_status("JSHint")

class JshintifyThread(threading.Thread):
    """ docstring for JshintifyThread """

    def __init__(self, view, errors, settings):
        super(JshintifyThread, self).__init__()

        self.view = view
        self.errors = errors
        self.settings = settings
        
        self.js_file_name = check_file(view) or None

        platform = sublime.platform()

        self.node_path = self.settings.get('paths')[platform]['node_path'] or 'node'
        self.jshint_path = self.settings.get("paths")[platform]['jshint_path'] or 'jshint'

        self.jshintrc = self.settings.get("jshintrc", None)

        for line in self.errors:
            self.view.erase_regions('jshintify.error.' + str(line))

    def run(self):
        """
        Run jshint
        """
        print self.js_file_name, self.node_path, self.jshint_path
        if None in [self.js_file_name, self.node_path, self.jshint_path]:
            return None

        command = self.create_command()
        
        proc = subprocess.Popen(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            startupinfo=STARTUPINFO)

        (out, err) = proc.communicate()

        if type(err) == bytes and len(err) > 0:
            raise Error(err)

        new_errors = json.loads(out.decode())

        # for line in new_errors:
        sublime.set_timeout(lambda: self.draw_lines(new_errors), 100)
        
        if len(new_errors) == 0:
            self.errors = {}
        else:
            self.errors.update(new_errors)

    def create_command(self):
        """
        Create command list
        """

        command = []

        command.append(self.node_path)
        command.append(self.jshint_path)
        
        command.append("--reporter")
        reporter_path = "{packages_dir}/jshintify/json-reporter.js".format(
                packages_dir = sublime.packages_path()
            )
        command.append(reporter_path)

        if self.jshintrc is not None:
            command.append("--config")
            command.append(self.jshintrc)

        command.append(self.js_file_name)

        return command

    def draw_lines(self, errors):
        """ Draw outline and/or 'dot'. """

        for line_number in errors:
            dot_sign = ''
            if SHOW_DOT:
                dot_sign = 'dot'

            draw_type = sublime.DRAW_OUTLINED
            if not SHOW_OUTLINE:
                draw_type = sublime.HIDDEN

            line = self.view.line(self.view.text_point(int(line_number) - 1, 0))
            self.view.add_regions('jshintify.error.' + str(line_number), [line],
                            'jshintify.error.' + str(line_number), dot_sign, draw_type)
    

def check_file(view):
    """
    Get current filename
    """

    js_file_name = ""
    if view.file_name() is not None:
        js_file_name = view.file_name()
    elif view.window() is not None and view.window().active_view().file_name() is not None:
        js_file_name = view.window().active_view().file_name()
    else:
        raise Error("This may be a bug, please create issue on github")

    if os.path.splitext(js_file_name)[1] not in EXTENSIONS:
        return False

    return js_file_name

class JshintifyQuickPanelCommand(sublime_plugin.TextCommand):#pylint: disable-msg=R0903,W0232
    """Command to clear the sniffer marks from the view"""
    description = 'Clear sniffer marks...'

    def run(self, edit):#pylint: disable-msg=R0903,W0232,W0613
        """
        Run plugin
        """
        row = self.view.rowcol(self.view.sel()[0].begin())[0]

        if str(row + 1) in ERRORS:
            error_data = []
            for error in ERRORS[str(row + 1)]:
                error_data.append(get_error_string(error))

            self.view.window().show_quick_panel(error_data, None, sublime.MONOSPACE_FONT)

def progress_tracker(thread, i=0):
    """ Show some stuff """

    icons = [u"◐", u"◓", u"◑", u"◒"]
    sublime.status_message("jshinting %s" % icons[i])
    if thread.is_alive():
        i = (i + 1) % 4
        sublime.set_timeout(lambda: progress_tracker(thread, i), 100)
    else:
        sublime.status_message("")

def get_error_string(error):
    """
    Return Error string
    """

    return "{id} : {reason}".format(id = error['id'], reason = error['reason'])

class Error(Exception):
    """
    Just generic error for module
    """
    pass