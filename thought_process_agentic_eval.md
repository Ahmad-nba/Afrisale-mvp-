Ok, I want to go onto the next stage of now fine tunning my agentic behavior knowing I can successfully reach it. I want to now ensure the output is to the desire. 
Act as a prompt engineer and help me fine tune this cusor prompt that is gona implement that for me; 
"Ok, now our flow test has been implemented. Now I want to set up a flow where I am fine tunning my agent , hence forth your gonna create a test_agent.py , this should ask for input from me and this will be the simulated user input lets say asking a series of questions and doing staff this input is entirely dependant on the user and we cannot predefine it so just put an input format for me in the console then when i input, take it in calling the agent and then we see how this agent internalises the information its dexission of tool calling basing on the infor, then this will give us a basis of fine tuning and engineering our prompts. "

So I have been watching something at Ycombinator start ups , How to build valuable AI applications. 
Now some of the things i have picked out, for you to solve a problem that your sure is worth, pick out something that people are already paying other people for to get it done. And this something is a process that is done repeatedly ie has a pattern of execution / expected pattern of completing to get the desired outcome. 
And with our Afrisale we already have proof of this, the inspiration of this whole project was a job opening for two people who were to help in making online sales by replying customers on whatsapp, and working to close orders.
Now when we go deeper on Evaluation ie how we deliver the value. 
We get the task and break it down to steps say the process of making online sales what our aim is (making the customers get a shop experience online in a conversational manner) So it would go like (this an off the head example that might require stffing) ;
- Salutations and Rapport establishment
- User either knows what they want already and goes for it by either providing a screenshot of this (copied from the advertisement platforms, {so we need scraping mechanisms that decipher provided screenshots to the db and understand what the user is infering to}
      - Telling the user about the availability of there request (variants, price ....)
      - We start stirring them to order (Would you like to make an order, Which do you like, )
      - Showing them similar products given they dont want to order that (Can I see other options available)
- User dont know exactly what they looking for (I want new balance 350)
   -Here we have more precise control as we show the user what is available regards their asked product. 
- Now for both cases we come to making them take an order, Here we now ask for location, when they want to get their order, Here would be a good time to layoff this to the store runner to patch in that order and set it on delivery.


Our biggest worries so far is the ability of scraping the user initiated image like ; Hey do you have this in stock, can the agent classify the image using a reliable mechanism map it to the database and return the item or a range of similar items. 

A solution we could have to ensure less frustration is rendering products from the order of latest upload to the store. 
