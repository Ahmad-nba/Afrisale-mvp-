### Title: Phase 2 problem. working with customization and improvement of the agent flow response. 

## current state, the agent takes in the info, processes it, calls tools but the tools and prompts are loosely coupled. 

##problem 1;
- We order for a existing atleast something that sould exist in the db, but the agent calls the tool and it says its not seeing it or it doesnot have it in its catalog. 
- Looks like the problem is exact matching zb. input===search yet users are sketchy, they will never input the exact product, so we need a allowance for allowed words that correspond to the key word. 

##The issue of prompts; 
- Here in parlant I see we are using quidelines, and they minimal, only two so far.
- and if we follow the Y-combinator approach, we need to write a prompt for each phase that is involved in our sales closure. But we handle this in an approach remembering this aint a graph. 
- The display aint showing quantity remaining even. 
-Remember the qnty only reduces when actually a product is set to delivery mode. That a whole another business logic.
- Then when we look at the *engine builder prompt fnxn*: the most important one in this case; ```{python}
    def _build_prompt(self, user_text: str, tool_result: str = "") -> str:
        guideline_lines = []
        for g in self.guidelines:
            guideline_lines.append(f"- {g}")
        tools_summary = []
        for t in self.tools:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name", "unknown_tool"))
            desc = str(t.get("description", ""))
            params = t.get("parameters", {})
            try:
                params_str = json.dumps(params, ensure_ascii=True)
            except Exception:
                params_str = "{}"
            tools_summary.append(f"- {name}: {desc} | params={params_str}")
        prompt = (
            f"You are Afrisale assistant for role={self.role}.\n"
            "Follow these guidelines strictly:\n"
            f"{chr(10).join(guideline_lines) if guideline_lines else '- (no guidelines provided)'}\n\n"
            "Available tools:\n"
            f"{chr(10).join(tools_summary) if tools_summary else '- (no tools provided)'}\n\n"
            f"User message:\n{(user_text or '').strip()}\n\n"
            f"{tool_result}"
            "Respond with the best helpful answer for this turn."
        )
        return prompt
```
We can see it runs one mega prompt to make the engine spin the runner. 
but from the standards of Y_combinator, we want a prompt per stage, yet this is parlant which might not be entirely a graph to work with. 

And then we also look at the guidelines; def customer_guidelines() -> list:
    """
    Returns Parlant guideline objects for customer-facing conversations.
    Intent: help customer browse catalog, search products, place orders.
    Must ask for delivery location before confirming any order.
    Must not quote prices not present in the DB.
    """
    return [
        "You are Afrisale, a friendly storefront assistant. Help customers browse products, search the catalog, and place orders.",
        "Always confirm the customer's delivery location before placing any order.",
        "Only quote prices that appear in the product catalog. Never estimate or approximate a price.",
        "If a customer asks about a product, use the search_products tool first rather than reciting the full catalog.",
        "Keep responses concise and suitable for WhatsApp — plain language, no more than 3-4 short paragraphs.",
    ]


def owner_guidelines() -> list:
    """
    Returns Parlant guideline objects for owner-facing conversations.
    Intent: add/update products, view orders, adjust stock and price.
    Must not expose other customers' data.
    """
    return [
        "You are Afrisale's owner assistant. Help manage the product catalog and review orders.",
        "You can add products, update stock, update prices, and list all orders.",
        "Never expose individual customer personal details beyond what is needed for order fulfilment.",
    ]


Q: we are tracing for behavior of the agent response on the it is responding and get ideas on how to fine tune the flow. Keeping in mind we are working with parlant. 








###The reference chat:
Ashlink@BIG-PROPELLER MINGW64 ~/DEV/projects/Afrisale(mvp) (main)
$ python agent_testV2.py
  Customer.phone_number detected as phone field

════════════════════════════════════════════════════════════════
  Afrisale — WhatsApp chat simulator
  Session started  14:47:39  │  Phone  +256700000001  │  Role  CUSTOMER
════════════════════════════════════════════════════════════════
  Type a message to begin. /help for commands.

You ▶  hey

You (000001)  14:47
  hey

Afrisale 📱  14:47
  Hi there! 👋 I'm Afrisale, your friendly storefront
  assistant. How can I help you today? Looking for something    
  specific, or just browsing?

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  intent   greeting            confidence  ████░░░░░░  43%      
  guard-in ✔ pass    guard-out ✔ pass
  tools    none called
  timing  guard-in 0ms  agent 6551ms  guard-out 3ms  total 6591ms
┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
You ▶  Kindly order for me a Tshirt and my delivery address is mubende. 

You (000001)  14:48
  Kindly order for me a Tshirt and my delivery address is
  mubende.

Afrisale 📱  14:48
  Hello there! I couldn't find any T-shirts in our catalog      
  right now.  Is there anything else I can help you find        
  today?

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  intent   delivery_info       confidence  ████████░░  80%      
  guard-in ✔ pass    guard-out ✔ pass
  tools
    → search_products  {"query": "Tshirt"}  (2ms)
  timing  guard-in 0ms  agent 6736ms  guard-out 3ms  total 6776ms
┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
You ▶  What do you have in your catalog

You (000001)  14:48
  What do you have in your catalog

Afrisale 📱  14:48
  Hello there! Here's what we have in our catalog right now:    
  **T-Shirts:** *   Black T-Shirt (M, Black) - 25,000 *
  Graphic T-Shirt (M, White) - 35,000; (L, Olive) - 36,000 *    
  Polo Shirt (M, Maroon) - 50,000; (XL, Navy) - 52,000
  **Bottoms:** *   Denim Jeans (32, Blue) - 85,000 *   Chinos   
  Trousers (32, Khaki) - 85,000; (34, Navy) - 88,000
  **Outerwear:** *   Denim Jacket (M, Blue) - 135,000; (L,      
  Black) - 140,000 *   Hoodie (M, Gray) - 90,000; (L, Black) -  
  92,000  **Shoes:** *   Sneakers (41, Black) - 95,000; (43,    
  White) - 98,000 *   Running Shoes (42, Blue) - 120,000; (44,  
  Gray) - 125,000  **Accessories:** *   Leather Belt (M,        
  Brown) - 40,000; (L, Black) - 42,000 *   Backpack (Standard,  
  Black) - 110,000; (Standard, Navy) - 112,000 *   Baseball     
  Cap (Standard, Black/Red) - 22,000  Let me know if anything   
  catches your eye, or if you'd like to search for something    
  specific!

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  intent   browse_catalog      confidence  ████████░░  85%      
  guard-in ✔ pass    guard-out ✔ pass
  tools
    → get_catalog  {}  (8ms)
  timing  guard-in 0ms  agent 8080ms  guard-out 4ms  total 8120ms
┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
You ▶
Session ended.


Interrupted.


Ashlink@BIG-PROPELLER MINGW64 ~/DEV/projects/Afrisale(mvp) (main)
$