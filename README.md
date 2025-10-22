# eXaMLab
<p align="center">
  <img src="https://github.com/user-attachments/assets/ebc66598-33e7-45d5-81a2-c241bd1d54f6"/>

</p>
<p>
  eXaMLab is a Python utility for writing Moodle content:
  <ul>
    <li>
    Question Banks in MoodleXML format
    </li>
    <li>
    Quiz (Placeholders)
    <br><i>Placeholders do not include questions or custom settings (point value e.g.)</i>
    </li>
  </ul>
</p>
<h2>Requirements</h2>
<p>The prepackaged versions under the Releases tab are fully portable, and avert the need to install anything.<br>
If running the script manually, which is not recommended, Python 3.12.x and above is required. Download Python at <a href="https://www.python.org/downloads/">python.org</a></p>
<h2>Installation</h2>
<p>
<ul><li>Windows users: install the latest version from the Releases tab and launch eXaMLab.exe</li>
<li>MacOS users: install the latest version from the releases tab and launch eXaMLab from \eXaMLab.app\Contents\MacOs</li></ul>
</p>
<h2>Features</h2>
<p>
  <ul>
  <li>Support for the most common question types:</li>
  <ol>
    <li>Multiple Choice</li>
    <li>True/False</li>
    <li>Short Answer</li>
    <li>Essay</li>
  </ol>
  <li>Question list GUI grows as you build your quiz; plainly see and edit questions you made earlier in the test bank</li>
  <li>Imports directly into Moodle as its own question category (name defined by you)</li>
  </ul>
</p>
<h2>Limitations</h2>
<p>
Images cannot be embedded into questions built with eXaMLab. To embed images, you must edit questions within Moodle after importing your .XML file. Loading an XML file that contains links to images is untested.
</p>
<p>
You cannot build these question types in eXaMLab:
</p>
<ul>
<li>
Drag and Drop
</li>
<li>
Calculated
</li>
<li>
Matching
</li>
<li>
Select Missing Words
</li>
<li>
Numerical
</li>
</ul>
<h2>What is Moodle XML?</h2>
<p>
  <b>MoodleXML</b> is a Moodle-specific format for writing questions to be used with the Quiz module.
  <br><br>
  Read more on MoodleDocs:
  <ul>
  <li>
<a href="https://docs.moodle.org/en/Moodle_XML_format">MoodleXML Format</a>
  </li>
  <li>
<a href="https://docs.moodle.org/en/Import_questions">Importing Questions into Moodle</a>
  </li>
  </ul>
</p>