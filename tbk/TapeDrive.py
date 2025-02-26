import datetime
import os
import tbk.TableOfContent as TableOfContent
import tbk.File as File
import xml.etree.ElementTree as ET

DEBUG: bool = False
VERSION = 4

class TapeDrive:
    
    status : int = 0
    
    def __init__(self, path_to_tape_drive: str) -> None:
        self.bs: str = "1M" # FIXME TODO
        self.drive_path: str = path_to_tape_drive
        
# ----------------BASIC I/O----------------------------------------------------
    
    def write(self, path_to_file: str, quiet: bool) -> None:
        _ec: int = 0    # Exit-Code
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # dd if='" + path_to_file + "' of="+ self.drive_path + " bs=" + self.bs)
            print("Quiet: " + str(quiet))
            return
        if quiet:
            _ec = os.system("dd if='" + path_to_file + "' of="+ self.drive_path + " bs=" + self.bs + " 2>/dev/null")
        else:
            _ec = os.system("dd if='" + path_to_file + "' of="+ self.drive_path + " bs=" + self.bs + " status=progress")
        if _ec != 0:
            raise
        
    def read(self, path_to_file: str, quiet: bool) -> None:
        _ec: int = 0    # Exit-Code
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # dd if=" + self.drive_path + " of='"+ path_to_file + "' bs=" + self.bs)
            print("[DEBUG] Quiet: " + str(quiet))
            return
        if quiet:
            _ec = os.system("dd if=" + self.drive_path + " of='"+ path_to_file + "' bs=" + self.bs + " 2>/dev/null")
        else:
            _ec = os.system("dd if=" + self.drive_path + " of='"+ path_to_file + "' bs=" + self.bs + " status=progress")
        if _ec != 0:
            raise

    def rewind(self) -> None:
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # mt -f " + self.drive_path + " rewind")
        else:
            os.system("mt -f " + self.drive_path + " rewind")
        
    def eject(self) -> None:
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # mt -f " + self.drive_path + " eject")
        else:
            os.system("mt -f " + self.drive_path + " eject")
            
# -----------------------------------------------------------------------------            

    #-------------------
    #TODO - REWORK
    #TODO - REWORK
    def dump_toc(self) -> None:
        _ec: int = 0    # Exit-Code
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # dd if=" + self.drive_path + " bs=" + self.bs + " | cat ")
        else:
            _ec = os.system("dd if=" + self.drive_path + " bs=" + self.bs + " | cat ")

        if _ec != 0:
            raise
    #-------------------
        
    def readTOC(self):
        # Steps:
        # 1. Read XML-File from Tape to /tmp/timestamp_toc-read.tmp
        # 2. Parse XML-File into ET.ElementTree
        # 3. Create TOC-Object, delete temporary File
        # 4. Return toc
        _xml_path: str = "/tmp/"+ datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_toc-read.tmp"
        self.rewind()
        self.read(_xml_path, True)
        xml_root: ET.Element = ET.parse(source=_xml_path).getroot()
        os.remove(_xml_path)
        return ET.tostring(xml_root)
    
    def xml2toc(self, path_to_xml: str) -> TableOfContent:
        self.rewind()
        # Read XML from Tape
        self.read(path_to_file=path_to_xml, quiet=True)
        # Try to parse File
        try:
            xml_root: ET.Element = ET.parse(source=path_to_xml).getroot()
        except:
            print("[ERROR] Could not parse Table of Contents: Invalid Format")
            print("Try 'tbk --dump | tbk -d'")
            exit(1)
        files: list[File] = []
        for index in range(1, len(xml_root)):
            try:                
                files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                size=int(str(xml_root[index][3].text)),
                                cksum_type=str(xml_root[index][4].text),
                                cksum=str(xml_root[index][5].text)
                ))
            except:
                files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                size=int(str(xml_root[index][3].text))
                ))
        _out: TableOfContent = TableOfContent(
            files=files,
            lto_version=str(xml_root[0][0].text),
            optimal_blocksize=str(xml_root[0][1].text),
            tape_sizeB=int(str(xml_root[0][2].text)),
            tbk_version=str(xml_root[0][3].text),
            last_modified=str(xml_root[0][4].text)
        )
        return _out

    
    def toc2xml(self, toc: TableOfContent, export_path: str) -> None:
        # Create XML-Root
        root = ET.Element("toc")
        # Append Header
        header: ET.Element = ET.SubElement(root, "header")
        ET.SubElement(header, "lto-version").text = toc.ltoV
        ET.SubElement(header, "optimal-blocksize").text = toc.bs
        ET.SubElement(header, "tape-size").text = str(toc.tape_size)
        ET.SubElement(header, "tbk-version").text = VERSION
        ET.SubElement(header, "last-modified").text = str(datetime.datetime.now())
        # Append Files
        for entry in toc.files:
            file: ET.Element = ET.SubElement(root, "file")
            ET.SubElement(file, "id").text = str(entry.id)
            ET.SubElement(file, "filename").text = entry.name
            ET.SubElement(file, "complete-path").text = entry.path
            ET.SubElement(file, "size").text = str(entry.size)
            ET.SubElement(file, "type").text = entry.cksum_type
            ET.SubElement(file, "value").text = entry.cksum
        
        xml_tree: ET.ElementTree = ET.ElementTree(element=root)
        try: 
            ET.indent(tree=xml_tree)
            xml_tree.write(file_or_filename=export_path, encoding="utf-8")
        except:
            raise NameError("[ERROR] Could not save Table of Contents!")
            
    def getStatus(self) -> int:
        
        """_stati_
        0   Error
        1   No Tape
        2   Tape RDY
        3   Tape RDY + WP
        4   Ejecting
        5   Writing
        6   Reading
        
        255 notImplemented
        """
        
        
        return 255
