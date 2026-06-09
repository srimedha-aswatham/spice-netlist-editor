import sys
import os
from datetime import datetime
import time
import re  

def stitch_netlist(input_filename, test_mode=False):
    """Step 1: Stitches lines ending in '\'. Handles Test Mode overwriting."""
    base_name, extension = os.path.splitext(input_filename)
    clean_base = base_name.split('_stitched_')[0]
    
    if test_mode:
        output_filename = f"{clean_base}_TEST_stitched{extension}"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{clean_base}_stitched_{timestamp}{extension}"

    print(f"\n[*] Starting Step 1: Stitching '{input_filename}'...")

    try:
        with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
            line_buffer = ""
            for line in infile:
                clean_line = line.rstrip('\r\n')
                if clean_line.endswith('\\'):
                    line_buffer += clean_line[:-1] + " "
                else:
                    line_buffer += clean_line
                    outfile.write(line_buffer + "\n")
                    line_buffer = ""

        print(f"[*] Step 1 Complete! Saved as: {output_filename}")
        return output_filename

    except FileNotFoundError:
        print(f"[!] Error: Could not find '{input_filename}'.")
        return None

def parse_components(filename):
    """Internal Engine: Reads a netlist and returns a dictionary of component counts."""
    component_data = {}
    try:
        with open(filename, 'r') as infile:
            for line in infile:
                line = line.strip()
                if not line or line.startswith(('*', '//', '.', 'subckt', 'ends')):
                    continue

                if ')' in line:
                    parts = line.split(')')
                    
                    instance_part = parts[0].strip()
                    if '(' in instance_part:
                        instance_name = instance_part.split('(')[0].strip()
                        first_letter = instance_name[0].upper()
                        
                        comp_type = "Unknown"
                        if first_letter == 'R': comp_type = "Resistor"
                        elif first_letter == 'C': comp_type = "Capacitor"
                        elif first_letter == 'M': comp_type = "MOSFET"
                        elif first_letter == 'D': comp_type = "Diode"
                        elif first_letter == 'X': comp_type = "PEX/Subckt"
                        elif first_letter == 'V': comp_type = "Voltage Src"
                        elif first_letter == 'I': comp_type = "Current Src"
                    else:
                        continue 

                    post_parens_text = parts[1].strip()
                    if post_parens_text:
                        words = post_parens_text.split()
                        model_name = words[0]
                        
                        if model_name[0].isdigit() or model_name[0] == '-' or model_name.replace('.','',1).isdigit():
                            model_name = f"[Ideal {comp_type}]"

                        if model_name in component_data:
                            component_data[model_name]["count"] += 1
                        else:
                            component_data[model_name] = {
                                "count": 1,
                                "type": comp_type
                            }
        return component_data
    except FileNotFoundError:
        return None

def generate_audit_report(original_file, modified_file=None, action_taken="None", test_mode=False):
    """Step 2: Generates a Before/After comparison report."""
    base_name, _ = os.path.splitext(original_file)
    clean_base = base_name.split('_TEST_')[0].split('_stitched_')[0] 
    
    if test_mode:
        output_filename = f"{clean_base}_TEST_AuditReport.txt"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{clean_base}_AuditReport_{timestamp}.txt"
    
    print(f"[*] Generating Component Audit Report...")

    orig_data = parse_components(original_file)
    mod_data = parse_components(modified_file) if modified_file else None

    if not orig_data:
        print("[!] Error: Could not generate report. Original file missing.")
        return False

    with open(output_filename, 'w') as outfile:
        outfile.write(f"=== NETLIST AUDIT REPORT ===\n")
        outfile.write(f"Action Taken: {action_taken}\n")
        outfile.write(f"Original File: {original_file}\n")
        if modified_file:
            outfile.write(f"Modified File: {modified_file}\n")
        outfile.write("=" * 75 + "\n\n")

        if modified_file and mod_data is not None:
            outfile.write(f"{'MODEL NAME':<30} | {'TYPE':<12} | {'BEFORE':<8} | {'AFTER':<8} | {'DELTA'}\n")
            outfile.write("-" * 75 + "\n")
            
            all_models = set(orig_data.keys()).union(set(mod_data.keys()))
            
            for model in sorted(all_models):
                type_name = orig_data.get(model, mod_data.get(model)).get("type", "Unknown")
                before_count = orig_data.get(model, {}).get("count", 0)
                after_count = mod_data.get(model, {}).get("count", 0)
                delta = after_count - before_count
                
                if delta > 0: delta_str = f"+{delta}"
                elif delta == 0: delta_str = "0"
                else: delta_str = str(delta)

                outfile.write(f"{model:<30} | {type_name:<12} | {before_count:<8} | {after_count:<8} | {delta_str}\n")
                
        else:
            outfile.write(f"{'MODEL NAME':<30} | {'TYPE':<12} | {'COUNT':<8}\n")
            outfile.write("-" * 55 + "\n")
            sorted_components = sorted(orig_data.items(), key=lambda item: item[1]["count"], reverse=True)
            for model, data in sorted_components:
                outfile.write(f"{model:<30} | {data['type']:<12} | {data['count']:<8}\n")

    print(f"[*] Audit Report saved to: {output_filename}")
    return True

def remove_by_device(input_filename, target_type, target_value, target_value_2=None, test_mode=False):
    """Step 3: Removes components strictly by Model, Instance, Component, or Inst_Model."""
    base_name, extension = os.path.splitext(input_filename)
    clean_base = base_name.split('_TEST_')[0].split('_stitched_')[0]
    
    if test_mode:
        output_filename = f"{clean_base}_TEST_modified{extension}"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if target_type == "inst_model":
            safe_target = f"{target_value}_{target_value_2}".replace('\\', '').replace('/', '_')
        else:
            safe_target = target_value.replace('\\', '').replace('/', '_')
        output_filename = f"{clean_base}_removed_{target_type}_{safe_target}_{timestamp}{extension}"
        
    removed_count = 0

    try:
        with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
            for line in infile:
                clean_line = line.strip()
                keep_line = True 

                if clean_line and not clean_line.startswith(('*', '//', '.', 'subckt', 'ends')):
                    
                    if target_type == "model":
                        if ')' in clean_line:
                            parts = clean_line.split(')')
                            if len(parts) > 1:
                                model_name = parts[1].strip().split()[0]
                                if model_name == target_value:
                                    keep_line = False
                                    removed_count += 1

                    elif target_type == "instance":
                        first_word = clean_line.split()[0]
                        target_folder = f"X{target_value}\\/" 
                        
                        if first_word.startswith(target_folder):
                            keep_line = False
                            removed_count += 1
                        elif len(first_word) > 1 and first_word[1:].startswith(target_folder):
                            keep_line = False
                            removed_count += 1

                    # SMART COMPONENT LOGIC
                    elif target_type == "component":
                        first_word = clean_line.split()[0]
                        clean_target = target_value.split('\\@')[0]
                        word_no_frac = first_word.split('\\@')[0]
                        
                        if '\\<' in clean_target:
                            base_name = word_no_frac 
                        else:
                            base_name = word_no_frac.split('\\<')[0]
                            
                        if base_name == clean_target:
                            keep_line = False
                            removed_count += 1

                    elif target_type == "inst_model":
                        first_word = clean_line.split()[0]
                        target_folder = f"X{target_value}\\/" 
                        
                        is_target_instance = False
                        if first_word.startswith(target_folder):
                            is_target_instance = True
                        elif len(first_word) > 1 and first_word[1:].startswith(target_folder):
                            is_target_instance = True
                            
                        if is_target_instance:
                            if ')' in clean_line:
                                parts = clean_line.split(')')
                                if len(parts) > 1:
                                    model_name = parts[1].strip().split()[0]
                                    if model_name == target_value_2: 
                                        keep_line = False
                                        removed_count += 1

                if keep_line:
                    outfile.write(line) 

        print(f"[*] File Processed. {removed_count} targeted lines removed.")
        return output_filename 
        
    except FileNotFoundError:
        print(f"[!] Error: Could not open '{input_filename}'.")
        return None
    
def modify_device(input_filename, target_type, target_value, target_value_2, params_to_change, test_mode=False):
    """Step 4: Modifies specific parameters of targeted components."""
    base_name, extension = os.path.splitext(input_filename)
    clean_base = base_name.split('_TEST_')[0].split('_stitched_')[0]
    
    if test_mode:
        output_filename = f"{clean_base}_TEST_modified{extension}"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if target_type == "inst_model":
            safe_target = f"{target_value}_{target_value_2}".replace('\\', '').replace('/', '_')
        else:
            safe_target = target_value.replace('\\', '').replace('/', '_')
        output_filename = f"{clean_base}_modified_{target_type}_{safe_target}_{timestamp}{extension}"
        
    modified_count = 0

    # Parse the user's parameter string (e.g., "wt=10e-06 lt=2e-06") into a dictionary
    param_dict = {}
    for pair in params_to_change.split():
        if '=' in pair:
            key, val = pair.split('=')
            param_dict[key] = val

    try:
        with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
            for line in infile:
                clean_line = line.strip()
                modify_this_line = False 

                if clean_line and not clean_line.startswith(('*', '//', '.', 'subckt', 'ends')):
                    
                    # Target Logic 1: MODEL
                    if target_type == "model":
                        if ')' in clean_line:
                            parts = clean_line.split(')')
                            if len(parts) > 1:
                                model_name = parts[1].strip().split()[0]
                                if model_name == target_value:
                                    modify_this_line = True

                    # Target Logic 2: INST_MODEL
                    elif target_type == "inst_model":
                        first_word = clean_line.split()[0]
                        target_folder = f"X{target_value}\\/" 
                        
                        is_target_instance = False
                        if first_word.startswith(target_folder) or (len(first_word) > 1 and first_word[1:].startswith(target_folder)):
                            is_target_instance = True
                            
                        if is_target_instance:
                            if ')' in clean_line:
                                parts = clean_line.split(')')
                                if len(parts) > 1:
                                    model_name = parts[1].strip().split()[0]
                                    if model_name == target_value_2: 
                                        modify_this_line = True

                # Apply the modifications if the line was targeted
                if modify_this_line:
                    modified_line = clean_line
                    for param, new_val in param_dict.items():
                        # Regex: Find "param=", optional spaces, then any non-space/non-parenthesis characters
                        pattern = rf"{param}\s*=\s*[^\s\)]+"
                        modified_line = re.sub(pattern, f"{param}={new_val}", modified_line)
                    
                    outfile.write(modified_line + "\n")
                    modified_count += 1
                else:
                    outfile.write(line) 

        print(f"[*] File Processed. {modified_count} targeted lines modified.")
        return output_filename 
        
    except FileNotFoundError:
        print(f"[!] Error: Could not open '{input_filename}'.")
        return None    

# --- Master Execution Pipeline ---
if __name__ == "__main__":
    
    test_mode_active = False
    if "--test" in sys.argv:
        test_mode_active = True
        sys.argv.remove("--test")
        print("\n[!] TEST MODE ACTIVE: Files will be overwritten.")

    if len(sys.argv) < 2:
        print("\n=== NETLIST EDITOR USAGE GUIDE ===")
        print("To run the editor, type 'python3 editor.py' followed by a command:")
        print("\n  [ANALYZE ONLY]")
        print("  python3 editor.py <netlist_file>")
        print("\n  [REMOVAL COMMANDS]")
        print("  remove model       <model>                <file> [--test]")
        print("  remove instance    <instance>             <file> [--test]")
        print("  remove component   <exact_comp>           <file> [--test]")
        print("  remove inst_model  <instance> <model>     <file> [--test]")
        print("\n  [MODIFY COMMANDS]")
        print("  modify model       <model> \"<params>\"       <file> [--test]")
        print("  modify inst_model  <inst> <model> \"<params>\" <file> [--test]")
        print("==================================\n")
        sys.exit()

    action_type = sys.argv[1].lower()
    
    # -----------------------------------------
    # ROUTER: REMOVE
    # -----------------------------------------
    if action_type == "remove":
        target_type = sys.argv[2].lower() 
        action_string = ""
        
        if target_type == "inst_model":
            if len(sys.argv) < 6:
                sys.exit("[!] Error: Missing arguments. See usage guide.")
            target_value, target_value_2, target_file = sys.argv[3], sys.argv[4], sys.argv[5] 
            action_string = f"Removed all '{target_value_2}' models inside instance '{target_value}'"
        else:
            if len(sys.argv) < 5:
                sys.exit("[!] Error: Missing arguments. See usage guide.")
            target_value, target_value_2, target_file = sys.argv[3], None, sys.argv[4]
            action_string = f"Removed entirely by {target_type}: '{target_value}'"
            
        stitched_file = stitch_netlist(target_file, test_mode=test_mode_active)
        
        if stitched_file:
            print(f"\n[*] Executing logic: {action_string}")
            clean_file = remove_by_device(stitched_file, target_type, target_value, target_value_2, test_mode=test_mode_active)
            if clean_file:
                time.sleep(0.5) 
                generate_audit_report(stitched_file, clean_file, action_string, test_mode=test_mode_active) 
                print("\n[+] Removal Pipeline execution finished successfully!")

    # -----------------------------------------
    # ROUTER: MODIFY
    # -----------------------------------------
    elif action_type == "modify":
        target_type = sys.argv[2].lower()
        action_string = ""
        
        if target_type == "inst_model":
            if len(sys.argv) < 7:
                sys.exit("[!] Error: Missing arguments. See usage guide.")
            target_value, target_value_2, params_to_change, target_file = sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
            action_string = f"Modified '{target_value_2}' in '{target_value}' -> [{params_to_change}]"
        elif target_type == "model":
            if len(sys.argv) < 6:
                sys.exit("[!] Error: Missing arguments. See usage guide.")
            target_value, target_value_2, params_to_change, target_file = sys.argv[3], None, sys.argv[4], sys.argv[5]
            action_string = f"Modified model '{target_value}' -> [{params_to_change}]"
        else:
            sys.exit("[!] Error: Modify currently only supports 'model' or 'inst_model'.")
            
        stitched_file = stitch_netlist(target_file, test_mode=test_mode_active)
        
        if stitched_file:
            print(f"\n[*] Executing logic: {action_string}")
            clean_file = modify_device(stitched_file, target_type, target_value, target_value_2, params_to_change, test_mode=test_mode_active)
            if clean_file:
                time.sleep(0.5) 
                # Note: Audit report will show '0' delta since the count didn't change, but it proves the file processed safely!
                generate_audit_report(stitched_file, clean_file, action_string, test_mode=test_mode_active) 
                print("\n[+] Modification Pipeline execution finished successfully!")

    # -----------------------------------------
    # ROUTER: ANALYZE
    # -----------------------------------------
    else:
        target_file = sys.argv[1]
        stitched_file = stitch_netlist(target_file, test_mode=test_mode_active)
        if stitched_file:
            time.sleep(0.5) 
            generate_audit_report(stitched_file, None, "Analysis Only", test_mode=test_mode_active)
            print("\n[+] Standard Pipeline execution finished successfully!")