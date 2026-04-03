### Testing the api endpoints in a browser.
    - The browser is by default to hit with GET request type
    - Testing manually https//<my_url>/endpoint and its a post request, It erros 405 (method not allowed). 
    So use curl to test on the end points in console. 

### Connection of the Twilio sandbox. 
    - Tunnel and make the endpoint discoverable.(ngrok, pingy, cloudflared)
    - Register the endpoint url in the sandbox sending (POST request)
    - Hit it by sending a message to the verified provided Twilio number using a verified sender. 