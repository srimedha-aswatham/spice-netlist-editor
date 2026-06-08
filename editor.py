import sys
import os
from datetime import datetime
import time

def stitch_netlist(input_filename):
    """Step 1: Stitches lines ending in '\' and returns the new filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name, extension = os.path.splitext(input_filename)
    output_filename = f"{base_name}_stitched_{timestamp}{extension}"

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
        return output_filename # Hand this name to the next step

    except FileNotFoundError:
        print(f"[!] Error: Could not find '{input_filename}'.")
        return None

def extract_component_list(input_filename):
    """Step 2: Analyzes the stitched file and generates a detailed component report."""
    base_name, _ = os.path.splitext(input_filename)
    clean_base = base_name.split('_stitched_')[0] 
    output_filename = f"{clean_base}_ComponentReport.txt"
    
    print(f"[*] Starting Step 2: Analyzing components in '{input_filename}'...")

    # Dictionary format: { "model_name": {"count": 1, "type": "Resistor", "params": "lr=... w=..."} }
    component_data = {}

    try:
        with open(input_filename, 'r') as infile:
            for line in infile:
                line = line.strip()
                if not line or line.startswith(('*', '//', '.', 'subckt', 'ends')):
                    continue

                if ')' in line:
                    parts = line.split(')')
                    
                    # 1. Grab the Instance Name to find the Component Type
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
                        continue # Skip malformed lines

                    # 2. Grab the Model and Values
                    post_parens_text = parts[1].strip()
                    if post_parens_text:
                        words = post_parens_text.split()
                        model_name = words[0]
                        
                        # The values are everything after the model name
                        params = " ".join(words[1:]) if len(words) > 1 else "None"

                        # Handle Ideal components (where the "model" is actually just the number value)
                        # e.g., "c1 ( n1 n2 ) 1.5e-15"
                        if model_name[0].isdigit() or model_name[0] == '-' or model_name.replace('.','',1).isdigit():
                            params = model_name # The value is the parameter
                            model_name = f"[Ideal {comp_type}]"

                        # 3. Add to our tracking dictionary
                        if model_name in component_data:
                            component_data[model_name]["count"] += 1
                        else:
                            component_data[model_name] = {
                                "count": 1,
                                "type": comp_type,
                                "params": params # Save the first instance's parameters as an example
                            }

        # --- Write the Beautifully Formatted Report ---
        with open(output_filename, 'w') as outfile:
            outfile.write(f"--- Component Summary ---\n")
            outfile.write(f"Source: {input_filename}\n\n")
            
            # Setup Column Headers
            outfile.write(f"{'MODEL NAME':<30} | {'TYPE':<12} | {'COUNT':<8} | {'EXAMPLE VALUES/PARAMS'}\n")
            outfile.write("-" * 90 + "\n")
            
            # Sort by count, highest to lowest
            sorted_components = sorted(component_data.items(), key=lambda item: item[1]["count"], reverse=True)
            
            for model, data in sorted_components:
                outfile.write(f"{model:<30} | {data['type']:<12} | {data['count']:<8} | {data['params']}\n")

        print(f"[*] Step 2 Complete! Report saved to: {output_filename}")
        return True

    except FileNotFoundError:
        print(f"[!] Error: Could not open '{input_filename}' for analysis.")
        return False

def remove_by_device(input_filename, target_type, target_value, target_value_2=None):
    """
    Step 3a: Removes components by Model, Instance, Component, or Inst_Model combination.
    """
    base_name, extension = os.path.splitext(input_filename)
    clean_base = base_name.split('_stitched_')[0]
    
    # Handle naming the output file cleanly if we have two targets
    if target_type == "inst_model":
        safe_target = f"{target_value}_{target_value_2}".replace('\\', '').replace('/', '_')
        print(f"\n[*] Starting Step 3a: Removing model '{target_value_2}' inside instance '{target_value}'...")
    else:
        safe_target = target_value.replace('\\', '').replace('/', '_')
        print(f"\n[*] Starting Step 3a: Removing {target_type} matching '{target_value}'...")
        
    output_filename = f"{clean_base}_removed_{target_type}_{safe_target}{extension}"

    removed_count = 0

    try:
        with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
            for line in infile:
                clean_line = line.strip()
                keep_line = True 

                if clean_line and not clean_line.startswith(('*', '//', '.', 'subckt', 'ends')):
                    
                    # 1. Remove by MODEL
                    if target_type == "model":
                        if ')' in clean_line:
                            parts = clean_line.split(')')
                            if len(parts) > 1:
                                model_name = parts[1].strip().split()[0]
                                if model_name == target_value:
                                    keep_line = False
                                    removed_count += 1

                    # 2. Remove by ENTIRE INSTANCE 
                    elif target_type == "instance":
                        first_word = clean_line.split()[0]
                        target_prefix = f"X{target_value}\\/" 
                        target_prefix_transistor = f"mX{target_value}\\/" 
                        if first_word.startswith(target_prefix) or first_word.startswith(target_prefix_transistor):
                            keep_line = False
                            removed_count += 1
                            
                    # 3. Remove by SPECIFIC COMPONENT 
                    elif target_type == "component":
                        first_word = clean_line.split()[0]
                        base_component_name = first_word.split('@')[0] 
                        if base_component_name == target_value:
                            keep_line = False
                            removed_count += 1

                    # 4. Remove by INSTANCE + MODEL (Your New Requirement!)
                    elif target_type == "inst_model":
                        first_word = clean_line.split()[0]
                        target_prefix = f"X{target_value}\\/" 
                        target_prefix_transistor = f"mX{target_value}\\/" 
                        
                        # First check: Is it inside the target instance?
                        if first_word.startswith(target_prefix) or first_word.startswith(target_prefix_transistor):
                            # Second check: Does it match the target model?
                            if ')' in clean_line:
                                parts = clean_line.split(')')
                                if len(parts) > 1:
                                    model_name = parts[1].strip().split()[0]
                                    if model_name == target_value_2: # Check against the second target!
                                        keep_line = False
                                        removed_count += 1

                if keep_line:
                    outfile.write(line) 

        # These two lines align with the 'with open...' statement
        print(f"[*] Done! {removed_count} devices removed. Saved to: {output_filename}")
        return output_filename 
        
    # This aligns perfectly with the 'try:' statement at the top
    except FileNotFoundError:
        print(f"[!] Error: Could not open '{input_filename}'.")
        return None
    

def remove_by_net(input_filename, target_net):
    """
    Step 3b: Removes ANY component that has a pin connected to the target net.
    """
    base_name, extension = os.path.splitext(input_filename)
    clean_base = base_name.split('_stitched_')[0]
    safe_target = target_net.replace('\\', '').replace('/', '_')
    output_filename = f"{clean_base}_removed_net_{safe_target}{extension}"
    
    print(f"\n[*] Starting Step 3b: Removing all components touching NET '{target_net}'...")
    removed_count = 0

    try:
        with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
            for line in infile:
                clean_line = line.strip()
                keep_line = True 

                if clean_line and not clean_line.startswith(('*', '//', '.', 'subckt', 'ends')):
                    # Look for the nodes inside the parentheses
                    if '(' in clean_line and ')' in clean_line:
                        start_idx = clean_line.find('(')
                        end_idx = clean_line.find(')')
                        if start_idx < end_idx:
                            nodes_string = clean_line[start_idx+1 : end_idx]
                            
                            # If the target net is found anywhere in the pin list, flag it for deletion
                            if target_net in nodes_string.split():
                                keep_line = False
                                removed_count += 1

                if keep_line:
                    outfile.write(line) 

        print(f"[*] Done! {removed_count} components connected to '{target_net}' removed. Saved to: {output_filename}")
        return output_filename 
    except FileNotFoundError:
        print(f"[!] Error: Could not open '{input_filename}'.")
        return None
    

def remove_subckt_definition(input_filename, target_subckt):
    """
    Step 3c: Removes an entire subcircuit blueprint (from .subckt to .ends).
    Uses a State Machine logic to track when it is inside the block.
    """
    base_name, extension = os.path.splitext(input_filename)
    clean_base = base_name.split('_stitched_')[0]
    output_filename = f"{clean_base}_removed_subckt_{target_subckt}{extension}"
    
    print(f"\n[*] Starting Step 3c: Hunting for blueprint '.subckt {target_subckt}'...")
    
    # This is our State Machine "Switch"
    inside_target_block = False 
    removed_line_count = 0

    try:
        with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
            for line in infile:
                # We use lower() to make our checks case-insensitive, just in case
                clean_line = line.strip().lower()

                # Check if this line is the START of the target subcircuit
                if clean_line.startswith('.subckt'):
                    parts = clean_line.split()
                    if len(parts) > 1 and parts[1] == target_subckt.lower():
                        print(f"[*] Found '.subckt {target_subckt}'. Flipping switch to DELETE MODE.")
                        inside_target_block = True

                # If the switch is ON, we are deleting
                if inside_target_block:
                    removed_line_count += 1
                    
                    # Check if this line is the END of the subcircuit
                    if clean_line.startswith('.ends'):
                        # Some SPICE files put the name after .ends, some don't. We handle both.
                        parts = clean_line.split()
                        if len(parts) == 1 or (len(parts) > 1 and parts[1] == target_subckt.lower()):
                            print(f"[*] Found '.ends'. Flipping switch back to KEEP MODE.")
                            inside_target_block = False # Turn the switch off!
                            
                    # We use 'continue' to immediately jump to the next line without writing
                    continue 
                
                # If the switch is OFF, we write the line normally
                outfile.write(line)

        print(f"[*] Done! Erased {removed_line_count} lines of the '{target_subckt}' blueprint. Saved to: {output_filename}")
        return output_filename 
        
    except FileNotFoundError:
        print(f"[!] Error: Could not open '{input_filename}'.")
        return None

# --- Master Execution Pipeline ---
if __name__ == "__main__":
    
    # 1. THE USAGE MENU
    if len(sys.argv) < 2:
        print("\n=== NETLIST EDITOR USAGE GUIDE ===")
        print("To run the editor, type 'python3 editor.py' followed by a command:")
        print("\n  [ANALYZE ONLY]")
        print("  python3 editor.py <netlist_file>")
        print("\n  [REMOVAL COMMANDS]")
        print("  remove model        <model_name>           <file>")
        print("  remove instance     <instance_name>        <file>")
        print("  remove component    <exact_comp_name>      <file>")
        print("  remove inst_model   <instance> <model>     <file>")
        print("  remove net          <net_name>             <file>")
        print("  remove subckt       <blueprint_name>       <file>")
        print("  remove purge_subckt <blueprint_name>       <file>")
        print("\n  [EXAMPLES]")
        print("  python3 editor.py remove purge_subckt MY_ADC_BLOCK my_chip.txt")
        print("==================================\n")
        sys.exit()

    # 2. Logic Router for Removal commands
    if sys.argv[1].lower() == "remove":
        target_type = sys.argv[2].lower() 
        
        # Handle the double-target feature
        if target_type == "inst_model":
            if len(sys.argv) < 6:
                print("[!] Error: Missing arguments for inst_model. See usage guide.")
                sys.exit()
            target_value = sys.argv[3]       
            target_value_2 = sys.argv[4]     
            target_file = sys.argv[5]        
        else:
            if len(sys.argv) < 5:
                print("[!] Error: Missing arguments. See usage guide.")
                sys.exit()
            target_value = sys.argv[3]
            target_value_2 = None            
            target_file = sys.argv[4]
            
        # Run Step 1: The Stitcher
        stitched_file = stitch_netlist(target_file)
        
        if stitched_file:
            # Route to the correct removal tool
            if target_type == "net":
                clean_file = remove_by_net(stitched_file, target_value)
                
            elif target_type == "subckt":
                clean_file = remove_subckt_definition(stitched_file, target_value)
                
            elif target_type == "purge_subckt":
                # --- THE COMBO MOVE ---
                print(f"\n[*] PURGE PROTOCOL INITIATED FOR '{target_value}'...")
                # 1. Destroy the instances (houses)
                step_1_file = remove_by_device(stitched_file, "model", target_value)
                # 2. Destroy the blueprint
                if step_1_file:
                    clean_file = remove_subckt_definition(step_1_file, target_value)
                    
            else:
                clean_file = remove_by_device(stitched_file, target_type, target_value, target_value_2)
                
            # Final Report Generation
            if clean_file:
                time.sleep(0.5) 
                extract_component_list(clean_file) 
                print("\n[+] Removal Pipeline execution finished successfully!")

    # 3. Standard Run (Just stitch and count)
    else:
        target_file = sys.argv[1]
        stitched_file = stitch_netlist(target_file)
        if stitched_file:
            time.sleep(0.5) 
            extract_component_list(stitched_file)
            print("\n[+] Standard Pipeline execution finished successfully!")