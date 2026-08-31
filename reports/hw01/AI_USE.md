# AI_USE.md — DATA-260 HW1 (SID4=1346)

## 1. What AI was used for vs. done independently

**What AI used in**
Assisted in generating ideas and providing guidance (for instance, the visual concept of transit signage, the starting structure of the Dockerfile)
Assisted in solving issues regarding the failure of the ECS deployment and enriched contextual knowledge concerning the Fargate message
Checked the code I prepared

**What was done without using AI**
Created the majority of the code in HTML, JS, and Python without the AI having the primary role of a developer in the creation process
Executed everything by myself in the terminal
Made all decisions concerning AWS on my own — cluster/service, security group policies, changes of the keys used
Carried out the conversation and the verification
Decided on the tags in Part 2

**A wrong AI output, and how I caught it**
An inaccurate output from the AI, and the method used in identifying the error
The Dockerfile for the AI executed successfully on the local machine; however, the ECS task aborted with exit code 255, which I found out through CloudWatch logs despite not consulting the AI
The finalize() method suggested by the AI relied on tags[:3], assuming that Reviewer would return at least 3 tags, although the test run produced only 2 unusual tags

**What I changed and why it works now**
The image was built again with docker buildx build --platform linux/amd64. The task was successfully confirmed to reach the Running state.
I created my own finalize() so I can patch up the missing tags based on those provided by the Planner instead of just bukly cutting.

 **Takeaway**
Creating the main logic on my own means I could truly comprehend the code and identify issues with the AI
AI is good at producing scaffolding and debugging but is not to be relied on for platform-specific issues (such as CPU architecture) or edge-case logic – it requires actual runs
The non-determinism present at temperature 0.7 made me realize that you cannot actually know if something works by visually checking its operation with only one run  there is a need for conducting 40 runs.
