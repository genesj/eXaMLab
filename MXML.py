import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import pandas as pd
import os
import logging

# Set up logging to log verbose error messages
logging.basicConfig(filename="error_log.txt", level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create a new toplevel window for the tooltip
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # Remove window decorations
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify='left', background='yellow', relief='solid', borderwidth=1, font=("tahoma", "10", "normal"))
        label.pack(ipadx=1)

    def hide_tooltip(self, event):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

class MoodleXMLBuilderApp:
    def __init__(self, root):
        try:
            self.root = root
            self.root.title("Moodle XML Question Builder")
            self.root.geometry("515x520")
            self.root.resizable(False, False)

            # Variables for tracking user input
            self.questions = []
            self.undo_stack = []
            self.edit_mode = False
            self.edit_index = None

            # Setup the user interface
            self.setup_ui()
        except Exception as e:
            logging.error("Error initializing the application", exc_info=True)

    def setup_ui(self):
        try:
            # Input field for question bank category
            self.label_category = tk.Label(self.root, text="Enter Question Bank Category:", anchor='e')
            self.label_category.grid(row=0, column=0, padx=10, pady=5, sticky='e')
            
            self.entry_category = tk.Entry(self.root, width=50)
            self.entry_category.grid(row=0, column=1, padx=10, pady=5)
            Tooltip(self.entry_category, "Enter the category name for the question bank. This will be added as a category in the XML.")

            # Dropdown for selecting the type of question to add
            self.label_question_type = tk.Label(self.root, text="Select Question Type:", anchor='e')
            self.label_question_type.grid(row=1, column=0, padx=10, pady=5, sticky='e')
            
            self.question_type_var = tk.StringVar(value="Multiple Choice")
            self.dropdown_question_type = ttk.Combobox(self.root, textvariable=self.question_type_var, values=["Multiple Choice", "True/False", "Short Answer", "Essay"])
            self.dropdown_question_type.bind("<<ComboboxSelected>>", lambda event: self.update_ui_for_question_type(self.question_type_var.get()))
            self.dropdown_question_type.state(["readonly"])  # Make it read-only to simulate an OptionMenu behavior
            self.dropdown_question_type.grid(row=1, column=1, padx=10, pady=5, sticky='w')
            Tooltip(self.dropdown_question_type, "Select the type of question you want to create.")

            # Input fields for question name and text
            self.label_question_name = tk.Label(self.root, text="Enter Question Name:", anchor='e')
            self.label_question_name.grid(row=2, column=0, padx=10, pady=5, sticky='e')
            
            self.entry_question_name = tk.Entry(self.root, width=50)
            self.entry_question_name.grid(row=2, column=1, padx=10, pady=5)
            Tooltip(self.entry_question_name, "Enter a unique name for the question.")
            
            self.label_question_text = tk.Label(self.root, text="Enter Question Text:", anchor='e')
            self.label_question_text.grid(row=3, column=0, padx=10, pady=5, sticky='e')
            
            self.entry_question_text = tk.Entry(self.root, width=50)
            self.entry_question_text.grid(row=3, column=1, padx=10, pady=5)
            Tooltip(self.entry_question_text, "Enter the main text for the question.")
            
            # Input for point value of the question
            self.label_points = tk.Label(self.root, text="Enter Point Value (default is 1):", anchor='e')
            self.label_points.grid(row=4, column=0, padx=10, pady=5, sticky='e')
            
            self.entry_points = tk.Entry(self.root, width=10)
            self.entry_points.grid(row=4, column=1, sticky='w', padx=10, pady=5)
            self.entry_points.insert(0, "1")  # Default value for points is 1
            Tooltip(self.entry_points, "Enter the point value for this question. Default is 1.")

            # Input fields for multiple choice questions
            self.label_mcq_options = tk.Label(self.root, text="Possible Choices:", anchor='e')
            self.label_mcq_options.grid(row=5, column=0, padx=10, pady=5, sticky='e')
            
            self.entry_mcq_options = tk.Entry(self.root, width=50)
            self.entry_mcq_options.grid(row=5, column=1, padx=10, pady=5)
            Tooltip(self.entry_mcq_options, "Enter the options for the multiple-choice question, separated by commas.")
            
            # Correct options for multiple choice questions
            self.label_correct_option = tk.Label(self.root, text="Correct Choice Number", anchor='e')
            self.label_correct_option.grid(row=6, column=0, padx=10, pady=5, sticky='e')
            
            self.entry_correct_option = tk.Entry(self.root, width=50)
            self.entry_correct_option.grid(row=6, column=1, padx=10, pady=5)
            Tooltip(self.entry_correct_option, "Enter the number(s) corresponding to the correct option(s), separated by commas.")

            # Input field for correct short answer
            self.label_short_answer_correct = tk.Label(self.root, text="Enter Correct Short Answer:", anchor='e')
            self.label_short_answer_correct.grid(row=7, column=0, padx=10, pady=5, sticky='e')
            self.entry_short_answer_correct = tk.Entry(self.root, width=50)
            self.entry_short_answer_correct.grid(row=7, column=1, padx=10, pady=5)
            Tooltip(self.entry_short_answer_correct, "Enter the correct answer for the short answer question.")

            # True/False question selection (radio buttons)
            self.label_tf_answer = tk.Label(self.root, text="Select True/False:", anchor='e')
            self.label_tf_answer.grid(row=8, column=0, padx=10, pady=5, sticky='e')
            self.tf_var = tk.StringVar(value="True")
            self.radio_true = tk.Radiobutton(self.root, text="True", variable=self.tf_var, value="True")
            self.radio_true.grid(row=8, column=1, sticky='w')
            self.radio_false = tk.Radiobutton(self.root, text="False", variable=self.tf_var, value="False")
            self.radio_false.grid(row=8, column=1, sticky='e')
            Tooltip(self.radio_true, "Select if the answer is True.")
            Tooltip(self.radio_false, "Select if the answer is False.")

            # Button for adding questions
            self.button_add_question = tk.Button(self.root, text="Add Question", command=self.add_question)
            self.button_add_question.grid(row=10, column=0, padx=10, pady=5, sticky='e')
            Tooltip(self.button_add_question, "Click to add the current question to the list.")

            # Button for editing questions
            self.button_edit_question = tk.Button(self.root, text="Edit Question", command=self.edit_question)
            self.button_edit_question.grid(row=10, column=1, padx=10, pady=5, sticky='w')

            # Button for deleting questions
            self.button_delete_question = tk.Button(self.root, text="Delete Question(s)", command=self.delete_selected_questions)
            self.button_delete_question.grid(row=10, column=1, padx=10, pady=5, sticky='e')
            Tooltip(self.button_delete_question, "Click to delete the selected questions from the list.")
            Tooltip(self.button_edit_question, "Click to edit the selected question from the list.")

            # Listbox to display all added questions
            self.listbox_questions = tk.Listbox(self.root, selectmode=tk.EXTENDED)
            self.listbox_questions.grid(row=11, column=0, columnspan=3, padx=10, pady=10, sticky='we')

            # Adjust column weight for listbox to stretch
            self.root.grid_columnconfigure(0, weight=1)
            self.root.grid_columnconfigure(1, weight=1)
            self.root.grid_columnconfigure(2, weight=1)

            # Button to save questions as XML
            self.button_save_xml = tk.Button(self.root, text="Save as XML", command=self.save_as_xml)
            self.button_save_xml.grid(row=12, column=0, columnspan=3, pady=5)
            Tooltip(self.button_save_xml, "Click to save all the questions as an XML file.")

            # Set initial UI state based on the selected question type
            self.update_ui_for_question_type("Multiple Choice")
        except Exception as e:
            logging.error("Error setting up the user interface", exc_info=True)

    def update_ui_for_question_type(self, question_type):
        try:
            # Make all specific widgets invisible initially
            self.label_mcq_options.grid()
            self.entry_mcq_options.grid()
            self.label_correct_option.grid()
            self.entry_correct_option.grid()
            self.label_short_answer_correct.grid()
            self.entry_short_answer_correct.grid()
            self.label_tf_answer.grid()
            self.radio_true.grid()
            self.radio_false.grid()

            # Hide the specific widgets by removing their content or visibility
            self.label_mcq_options.grid_remove()
            self.entry_mcq_options.grid_remove()
            self.label_correct_option.grid_remove()
            self.entry_correct_option.grid_remove()
            self.label_short_answer_correct.grid_remove()
            self.entry_short_answer_correct.grid_remove()
            self.label_tf_answer.grid_remove()
            self.radio_true.grid_remove()
            self.radio_false.grid_remove()

            # Show the relevant widgets based on the selected question type
            if question_type == "Multiple Choice":
                self.label_mcq_options.grid()
                self.entry_mcq_options.grid()
                self.label_correct_option.grid()
                self.entry_correct_option.grid()
            elif question_type == "True/False":
                self.label_tf_answer.grid()
                self.radio_true.grid()
                self.radio_false.grid()
            elif question_type == "Short Answer":
                self.label_short_answer_correct.grid()
                self.entry_short_answer_correct.grid()
        except Exception as e:
            logging.error("Error updating UI for question type", exc_info=True)

    def add_question(self):
        try:
            # Gather input values for the question
            question_type = self.question_type_var.get()
            question_name = self.entry_question_name.get()
            question_text = self.entry_question_text.get()
            points = self.entry_points.get()
            points = float(points) if points else 1.0  # Default to 1 point if not specified

            # Handle adding a multiple-choice question
            if question_type == "Multiple Choice":
                options_text = self.entry_mcq_options.get()
                correct_options_text = self.entry_correct_option.get()
                if question_name and question_text and options_text and correct_options_text:
                    options = [opt.strip() for opt in options_text.split(',')]  # Split and trim options
                    correct_options = [int(opt.strip()) for opt in correct_options_text.split(',')]  # Parse correct option numbers
                    question = {
                        "type": "Multiple Choice",
                        "name": question_name,
                        "text": question_text,
                        "options": options,
                        "correct": correct_options,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name, text, options, and correct answer(s).")
                    return
            # Handle adding a True/False question
            elif question_type == "True/False":
                tf_answer = self.tf_var.get()
                if question_name and question_text:
                    question = {
                        "type": "True/False",
                        "name": question_name,
                        "text": question_text,
                        "answer": tf_answer,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name and text.")
                    return
            # Handle adding a Short Answer question
            elif question_type == "Short Answer":
                correct_answer = self.entry_short_answer_correct.get()
                if question_name and question_text and correct_answer:
                    question = {
                        "type": "Short Answer",
                        "name": question_name,
                        "text": question_text,
                        "correct_answer": correct_answer,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name, text, and correct answer.")
                    return
            # Handle adding an Essay question
            elif question_type == "Essay":
                if question_name and question_text:
                    question = {
                        "type": "Essay",
                        "name": question_name,
                        "text": question_text,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name and text.")
                    return

            if self.edit_mode:
                # Overwrite the existing question if in edit mode
                self.questions[self.edit_index] = question
                self.edit_mode = False
                self.edit_index = None
            else:
                # Otherwise, add the question to the list
                self.questions.append(question)
            
            self.update_question_list()  # Update listbox
            self.clear_entries()  # Clear input fields
        except Exception as e:
            logging.error("Error adding question", exc_info=True)

    def clear_entries(self):
        try:
            # Clear all the input fields to prepare for the next question
            self.entry_question_name.delete(0, tk.END)
            self.entry_question_text.delete(0, tk.END)
            self.entry_points.delete(0, tk.END)
            self.entry_points.insert(0, "1")  # Reset point value to default of 1
            self.entry_mcq_options.delete(0, tk.END)
            self.entry_correct_option.delete(0, tk.END)
            self.entry_short_answer_correct.delete(0, tk.END)
            self.edit_mode = False
            self.edit_index = None
        except Exception as e:
            logging.error("Error clearing entries", exc_info=True)

    def delete_selected_questions(self):
        try:
            # Delete the selected questions from the listbox and the questions list
            selected_indices = list(self.listbox_questions.curselection())
            selected_indices.reverse()  # Reverse to avoid indexing issues when deleting
            for index in selected_indices:
                del self.questions[index]  # Remove the question from the list
            self.update_question_list()  # Update the listbox display
        except Exception as e:
            logging.error("Error deleting selected questions", exc_info=True)

    def update_question_list(self):
        try:
            # Update the listbox to reflect the current list of questions
            self.listbox_questions.delete(0, tk.END)  # Clear the listbox
            for question in self.questions:
                # Create a display string for each question
                display_text = f"{question['type']}: {question['name']} - {question['text']} (Points: {question['points']})"
                self.listbox_questions.insert(tk.END, display_text)  # Add the question to the listbox
        except Exception as e:
            logging.error("Error updating question list", exc_info=True)

    def save_as_xml(self):
        try:
            # Save all questions to an XML file
            if not self.questions:
                messagebox.showwarning("Save Error", "No questions to save.")
                return
            
            # Prompt user for file save location
            file_path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML files", "*.xml")])
            if not file_path:
                return

            # Create XML structure and save it
            xml_content = self.create_xml_content()

            # Write the XML content to the selected file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(xml_content)

            messagebox.showinfo("Save Successful", f"Questions saved to {os.path.basename(file_path)}")
        except Exception as e:
            logging.error("Error saving questions as XML", exc_info=True)

    def create_xml_content(self):
        try:
            # Create XML content string
            xml_content = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<quiz>\n"

            # Add category to the XML if specified
            category_name = self.entry_category.get().strip()
            if category_name:
                xml_content += f"  <question type=\"category\">\n    <category>\n      <text>$course$/{category_name}</text>\n    </category>\n  </question>\n"

            # Add each question to the XML content
            for question in self.questions:
                if question['type'] == "Multiple Choice":
                    xml_content += f"  <question type=\"multichoice\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n"
                    for idx, option in enumerate(question['options'], start=1):
                        fraction = "100" if idx in question['correct'] else "0"
                        xml_content += f"    <answer fraction=\"{fraction}\">\n      <text>{option}</text>\n    </answer>\n"
                    xml_content += "  </question>\n"
                elif question['type'] == "True/False":
                    correct_value = "true" if question['answer'] == "True" else "false"
                    xml_content += f"  <question type=\"truefalse\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n    <answer fraction=\"100\">\n      <text>{correct_value}</text>\n    </answer>\n    <answer fraction=\"0\">\n      <text>{'false' if correct_value == 'true' else 'true'}</text>\n    </answer>\n  </question>\n"
                elif question['type'] == "Short Answer":
                    xml_content += f"  <question type=\"shortanswer\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n    <answer fraction=\"100\">\n      <text>{question['correct_answer']}</text>\n    </answer>\n  </question>\n"
                elif question['type'] == "Essay":
                    xml_content += f"  <question type=\"essay\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n  </question>\n"
            xml_content += "</quiz>"

            return xml_content
        except Exception as e:
            logging.error("Error creating XML content", exc_info=True)
            return ""

    def edit_question(self):
        try:
            selected_indices = list(self.listbox_questions.curselection())
            if len(selected_indices) != 1:
                messagebox.showwarning("Edit Error", "Please select exactly one question to edit.")
                return

            index = selected_indices[0]
            question = self.questions[index]

            # Populate the fields with the selected question's data
            self.question_type_var.set(question['type'])
            self.update_ui_for_question_type(question['type'])
            self.entry_question_name.delete(0, tk.END)
            self.entry_question_name.insert(0, question['name'])
            self.entry_question_text.delete(0, tk.END)
            self.entry_question_text.insert(0, question['text'])
            self.entry_points.delete(0, tk.END)
            self.entry_points.insert(0, str(question['points']))

            if question['type'] == "Multiple Choice":
                self.entry_mcq_options.delete(0, tk.END)
                self.entry_mcq_options.insert(0, ', '.join(question['options']))
                self.entry_correct_option.delete(0, tk.END)
                self.entry_correct_option.insert(0, ', '.join(map(str, question['correct'])))
            elif question['type'] == "True/False":
                self.tf_var.set(question['answer'])
            elif question['type'] == "Short Answer":
                self.entry_short_answer_correct.delete(0, tk.END)
                self.entry_short_answer_correct.insert(0, question['correct_answer'])

            # Set edit mode to true and remember the index being edited
            self.edit_mode = True
            self.edit_index = index
        except Exception as e:
            logging.error("Error editing question", exc_info=True)

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = MoodleXMLBuilderApp(root)
        root.mainloop()
    except Exception as e:
        logging.error("Fatal error in main application loop", exc_info=True)
