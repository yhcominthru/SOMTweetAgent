import os
import sys
from dotenv import load_dotenv
import time

load_dotenv('environment.env')

base_sdk_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 
    "game-python-main",
    "game-python",
    "game_sdk"
)
sys.path.append(base_sdk_path)

game_sdk_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 
    "game-python-main",
    "game-python"
)
sys.path.append(game_sdk_path)

# Add the plugins/stateofmika directory specifically
stateofmika_path = os.path.join(game_sdk_path, "plugins", "stateofmika")
print("Adding stateofmika path:", stateofmika_path)
sys.path.append(stateofmika_path)

# Add twitter plugin path
twitter_path = os.path.join(game_sdk_path, "plugins", "twitter")
sys.path.append(twitter_path)

from game_sdk.game.agent import Session, Agent, WorkerConfig
from game_sdk.game.custom_types import FunctionResult
from stateofmika_plugin_gamesdk.functions.router import SOMRouter
from twitter_plugin_gamesdk.twitter_plugin import TwitterPlugin

# Set up Twitter plugin
twitter_options = {
    "id": "twitter_agent",
    "name": "Twitter Bot",
    "description": "A Twitter bot that posts updates",
    "credentials": {
        "bearerToken": os.environ.get("TWITTER_BEARER_TOKEN"),
        "apiKey": os.environ.get("TWITTER_API_KEY"),
        "apiSecretKey": os.environ.get("TWITTER_API_SECRET"),
        "accessToken": os.environ.get("TWITTER_ACCESS_TOKEN"),
        "accessTokenSecret": os.environ.get("TWITTER_ACCESS_SECRET")
    }
}

twitter_plugin = TwitterPlugin(twitter_options)

# Function to update agent state
def get_agent_state_fn(function_result: FunctionResult, current_state: dict) -> dict:
    if current_state is None:
        current_state = {}
    
    # Initialize if not exists
    if "previous_queries" not in current_state:
        current_state["previous_queries"] = []
    if "previous_routes" not in current_state:
        current_state["previous_routes"] = []
    if "current_task" not in current_state:
        current_state["current_task"] = None

    if function_result and function_result.info:
        current_state["previous_queries"].append(function_result.info.get("query", ""))
        current_state["previous_routes"].append(function_result.info.get("route", {}))

    return current_state

# Define the worker for querying State of Mika
mika_router = SOMRouter()

def create_worker_config(functionality_name, description):
    # Create the basic worker config without query_template
    return WorkerConfig(
        id="som_router",
        worker_description=f"Worker specialized in {functionality_name}. {description}",
        get_state_fn=get_agent_state_fn,
        action_space=[mika_router.get_function()],
    )

# Menu of available functionalities
functionalities = {
    '1': ('Token Information', 'Get token prices and market data'),
    '2': ('Crypto News', 'Fetch latest crypto news and updates'),
    '3': ('Web Scraping', 'Get data from specified websites')
}

def format_tweet(functionality_name, query, response):
    tweet_text = f"🚀 Mika Update | {functionality_name}:\n\n"
    tweet_text += f"Query: {query}\n"
    
    # Handle different response types and lengths
    response_text = str(response)
    if functionality_name == "Web Scraping":
        # For web scraping, create a more concise summary
        max_length = 150  # Even shorter for web content
        if len(response_text) > max_length:
            sentences = response_text.split('.')
            summary = sentences[0].strip()  # Take first sentence
            if len(summary) > max_length:
                summary = summary[:max_length-3] + "..."
            response_text = summary
    else:
        # For other functionalities
        max_length = 200
        if len(response_text) > max_length:
            response_text = response_text[:max_length-3] + "..."
    
    tweet_text += f"Result: {response_text}\n\n"
    tweet_text += get_hashtags(functionality_name)
    return tweet_text

def create_agent_with_retry(api_key, name, agent_goal, agent_description, get_agent_state_fn, workers):
    max_retries = 3
    base_delay = 30  # Increased to 30 seconds for rate limits
    
    for attempt in range(max_retries):
        try:
            agent = Agent(
                api_key=api_key,
                name=name,
                agent_goal=agent_goal,
                agent_description=agent_description,
                get_agent_state_fn=get_agent_state_fn,
                workers=workers,
            )
            agent.compile()
            return agent
        except ValueError as e:
            if "Too Many Requests" in str(e) or "429" in str(e):
                wait_time = base_delay * (2 ** attempt)  # 30s, 60s, 120s
                print(f"\nRate limit hit. Cooling down...")
                print(f"Attempt {attempt + 1}/{max_retries}. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    print("\nStill rate limited. Suggestions:")
                    print("1. Wait a few minutes before trying again")
                    print("2. Reduce the frequency of your requests")
                    print("3. Check your API usage limits")
            else:
                print(f"Error creating agent: {str(e)}")
            if attempt == max_retries - 1:
                raise

def post_tweet_with_retry(tweet_text):
    max_retries = 3
    base_delay = 30  # seconds
    
    for attempt in range(max_retries):
        try:
            post_tweet = twitter_plugin.get_function('post_tweet')
            post_tweet(tweet_text)
            print("Tweet posted:", tweet_text)
            return True
        except Exception as e:
            if "429 Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)  # Exponential backoff: 30s, 60s, 120s
                    print(f"Rate limited by Twitter. Attempt {attempt + 1}/{max_retries}. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
            elif "403 Forbidden" in str(e):
                print(f"Tweet too long or formatting issue. Truncating further...")
                if len(tweet_text) > 280:  # Twitter's character limit
                    tweet_text = tweet_text[:277] + "..."
                continue
            else:
                print(f"Failed to post tweet: {str(e)}")
                return False
    return False

def get_hashtags(functionality_name):
    """Get relevant hashtags based on the functionality"""
    hashtags = "#StateOfMika"
    if functionality_name == 'Token Information':
        hashtags += " #Crypto #Price"
    elif functionality_name == 'Crypto News':
        hashtags += " #CryptoNews"
    elif functionality_name == 'Web Scraping':
        hashtags += " #WebData"
    return hashtags

def format_query(query: str, functionality_name: str) -> str:
    """Format the query based on functionality type"""
    if functionality_name == 'Token Information':
        # Add specific formatting for token queries
        if 'price' in query.lower():
            return f"Get detailed price information including market cap for {query.split()[-1]}"
        return f"Get token information and market data for {query}"
    return query

def log_api_response(result, query):
    """Log detailed API response for debugging"""
    print("\nAPI Response Details:")
    print(f"Original Query: {query}")
    print(f"Action Status: {result.action_status}")
    if result.feedback_message:
        print(f"Feedback: {result.feedback_message}")
    if result.info:
        print("Response Info:")
        for key, value in result.info.items():
            print(f"  {key}: {value}")
    print("-" * 50)

def handle_api_error(error_msg: str, query: str, functionality_name: str) -> tuple[bool, str]:
    """Handle API errors and suggest alternative approaches"""
    if "500" in str(error_msg):
        print("\nAPI Error Analysis:")
        print("1. Original query might be too complex")
        print("2. API endpoint might be temporarily unavailable")
        print("3. Token data might need different formatting")
        
        # Try reformatting the query
        return True, format_query(query, functionality_name)
    return False, query

def run_agent_and_tweet():
    print("Starting State of Mika API interaction...")
    
    while True:
        print("\nAvailable functionalities:")
        for key, (name, desc) in functionalities.items():
            print(f"{key}: {name} - {desc}")
        print("0: Exit")
        
        choice = input("\nSelect functionality (0-3): ")
        if choice == '0':
            break
            
        original_query = input("Enter your query: ")
        query = format_query(original_query, functionalities.get(choice, ('Query', ''))[0])
        
        # Get functionality details
        functionality_name, description = functionalities.get(choice, ('Query', ''))
        
        # Create a new agent for each query with specific functionality
        worker = create_worker_config(functionality_name, description)
        
        try:
            agent = create_agent_with_retry(
                api_key=os.environ["GAME_API_KEY"],
                name=f"Mika {functionality_name} Agent",
                agent_goal=f"Process {functionality_name.lower()} queries",
                agent_description=f"Specialized in {description.lower()}",
                get_agent_state_fn=get_agent_state_fn,
                workers=[worker],
            )
        except ValueError as e:
            print(f"Error creating agent: {str(e)}")
            if input("\nRetry? (y/n): ").lower() != 'y':
                break
            continue
        
        # Initialize session and set state
        agent._session = Session()
        agent.agent_state = {
            "current_task": query,
            "functionality": functionality_name,
            "previous_queries": [],
            "previous_routes": []
        }
        
        print(f"\nProcessing query: {query}")
        
        max_retries = 3
        base_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                agent.step()
                result = agent._session.function_result
                
                # Log detailed response for debugging
                log_api_response(result, query)
                
                if result:
                    if result.action_status == "done":
                        response = result.info.get("response", {}).get("processed_response", "Unable to fetch data")
                        tweet_text = format_tweet(functionality_name, query, response)
                        
                        if post_tweet_with_retry(tweet_text):
                            time.sleep(5)
                            break
                        break
                    elif result.action_status == "failed":
                        error_msg = result.feedback_message
                        print(f"\nAPI Error: {error_msg}")
                        
                        if attempt < max_retries - 1:
                            wait_time = base_delay * (2 ** attempt)
                            print(f"Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print("\nAll retry attempts failed. Please try:")
                            print("1. A different query format")
                            print("2. Waiting a few minutes")
                            print("3. Checking the API status")
                            break
                else:
                    print("\nNo result received from the API")
                    break
                
            except Exception as e:
                print(f"\nUnexpected error: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(base_delay)
                    continue
                break
        
        if input("\nContinue? (y/n): ").lower() != 'y':
            break

if __name__ == "__main__":
    run_agent_and_tweet()
