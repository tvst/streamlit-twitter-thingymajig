# Streamlit Twitter thingymajig

A tweet analysis dashboard written in Streamlit!

See it in action:

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/tvst/streamlit-twitter-thingymajig/main)

# Trying this in your own machine

To try it out, you first need to specify your Twitter API credentials:

1. Create a subfolder _in this repo_, called `.streamlit`
2. Create a file at `.streamlit/secrets.toml` file with the following body:
   ```toml
   [twitter]
   # Enter your secrets here. See README.md for more info.
   consumer_key = 'enter your credentials here'
   consumer_secret = 'enter your credentials here'
   ```
3. Go to the [Twitter Developer Portal](https://developer.twitter.com/en/portal), create or select an existing project + app, then go to the app's "Keys and Tokens" tab to generate your "Consumer Keys".
4. Copy and paste you key and secret into the file above.
5. Now you can run you Streamlit app as usual:
   ```
   streamlit run streamlit_app.py
   ```

## Important

The current version of this app uses some _very alpha_ features of Streamlit. If you clone this repo, be aware that these features will be changing dramatically before they land. You've been warned! 
