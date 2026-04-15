# Macro Tracker

Macro Tracker is designed to help users track their macronutrient intake by simply taking a picture of their meals. 
It leverages the power of the backing AI model to analyze meal images and provide an estimated breakdown of total calories, protein, carbohydrates, and fats; time stamping the meal.

Similar to the AI Cycling coach, there is a dedicated Nutritionist as a different coach, it could talk to the cycling coach via Google Agent Development kit's Agent2Agent protocol to get data or offer guidance as it relates to workouts, nutrition notes in rides etc… cycling coach might vice versa need to talk to nutritionist and check and see if I have enough fuel in board leading up to a big workout, etc ... also when planning workout notes for longer endurance rides; giving tips from the nutritionist in the workout notes about when and how many cals to consume, etc...


The core purpose is to simplify the process of food logging and be able to track input calories along output calories from the rides.

Instead of manually entering ingredients and quantities, users can snap a photo of their meal, optionally add a voice comment, and let the application do the rest. The backend service communicates with the model to get a detailed nutritional analysis, which is then stored and presented to the user.

If the image isn't clear, the nutritionist can ask clarifying details, but should try really hard to just figure it out, it can also look at eating habits, repeat meals and figure things out.

the user can always go in and edit the details

Macronutrient Breakdown: Provides an estimated breakdown of:
Calories
Protein (grams)
Carbohydrates (grams)
Fat (grams)
Structured Data: The analysis results are stored in the database and time stamped
Long-Term Storage: Meal photos are securely stored in a Google Cloud Storage (GCS) bucket for future reference.
Meal History: Users can view a history of their logged meals and track their nutritional intake over time and compare it to their output.  This data can be used by the AI coaches in their analysis.