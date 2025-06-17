const AuthenticationController = require("./controllers/AuthenticationController")
const AuthenticationControllerPolicy = require("./controllers/AuthenticationControllerPolicy")
const JwtTokenVerifier = require("./controllers/JwtTokenVerifier")
const ApiTokenVerifier = require("./controllers/ApiTokenVerifier")
const QuizController = require("./controllers/QuizController")
const axios = require("axios");
const API_BASE = "http://localhost:8081";

module.exports = (app) => {
    app.post("/register",
        AuthenticationControllerPolicy.register,
        AuthenticationController.register)

    app.post("/login",
        AuthenticationController.login)

    app.post("/refresh/logout",
        AuthenticationController.logout)

    app.post("/refresh/delete_account",
        AuthenticationController.delete_account)

    app.post("/refresh",
        JwtTokenVerifier.refreshTokenVerify)

    app.post("/quiz/create",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.createQuiz)

    app.get("/quizzes",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.getQuizzesForUser)

    app.get("/quiz/:quizId",
        QuizController.getQuiz)

    app.post("/quiz/:quizId/attempt",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.startQuizAttempt)

    app.post("/quiz/attempt/:attemptId/complete",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.completeQuizAttempt)

    app.get("/quiz/attempt/:attemptId/results",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.getAttemptResults)

    app.get("/user/quiz-attempts",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.getUserQuizAttempts)

    app.get("/course-categories",
        QuizController.getCourseCategories)

    app.post("/quiz/create-ai",
        JwtTokenVerifier.accessTokenVerify,
        QuizController.createAIQuiz)

    app.post("/quiz/create-ai-from-course",
        QuizController.createAIQuiz)

    app.get("/quizzes/:userId/from-course",
        ApiTokenVerifier.verifyApiToken,
        QuizController.getQuizzesForUser)    
        
    app.get("/quiz/:quizId/from-course",
        ApiTokenVerifier.verifyApiToken,
        QuizController.getQuiz)
    
    app.post("/quiz/:quizId/:userId/attempt-from-course",
        ApiTokenVerifier.verifyApiToken,
        QuizController.startQuizAttempt)

    app.post("/quiz/attempt/:attemptId/:userId/complete-from-course",
        ApiTokenVerifier.verifyApiToken,
        QuizController.completeQuizAttempt)

    app.get("/quiz/attempt/:attemptId/:userId/results-from-course",
        ApiTokenVerifier.verifyApiToken,
        QuizController.getAttemptResults)

    app.get("/user/:userId/quiz-attempts-from-course",
        ApiTokenVerifier.verifyApiToken,
        QuizController.getUserQuizAttempts)

    app.get(
      "/course/:courseId/quiz-recommendations",
      ApiTokenVerifier.verifyApiToken,
      async (req, res) => {
        try {
          const { courseId } = req.params;
          const userId = req.verifiedAccessToken.id;             // <- pull from token
          const headers = { Authorization: `Bearer ${process.env.API_ACCESS_TOKEN}` };

          // proxy the two “from-course” endpoints
          const [qRes, aRes] = await Promise.all([
            axios.get(`${API_BASE}/quizzes/${userId}/from-course`,   { headers }),
            axios.get(`${API_BASE}/user/${userId}/quiz-attempts-from-course`, { headers })
          ]);

          // now filter by courseId and return one JSON
          const quizzes  = qRes.data.quizzes.filter(q => q.courseId === courseId);
          const attempts = aRes.data.attempts.filter(a => a.quiz.courseId === courseId);
          res.json({ quizzes, attempts });
        } catch (err) {
          console.error(err);
          res.status(500).json({ error: "Failed to fetch recommendations" });
        }
      }
    )

    // Test endpoint for external API authentication
    app.get("/test-quiz-auth",
        ApiTokenVerifier.verifyApiToken,
        (req, res) => {
            res.status(200).json({ 
                message: "Authentication successful",
                timestamp: new Date().toISOString()
            })
        })
}